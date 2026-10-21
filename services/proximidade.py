"""Cobertura geohash de uma circunferência, seguida de distância exata."""
import math
import pygeohash
from google.cloud.firestore_v1.base_query import FieldFilter


class Proximidade:
    RAIO_TERRA = 6371.0

    @staticmethod
    def validar(latitude, longitude, raio):
        try:
            if any(isinstance(v, bool) for v in (latitude, longitude, raio)):
                raise ValueError()
            lat, lon, km = map(float, (latitude, longitude, raio))
            if not all(math.isfinite(v) for v in (lat, lon, km)):
                raise ValueError()
            if not (-90 <= lat <= 90 and -180 <= lon <= 180 and 0 <= km <= 100):
                raise ValueError()
        except (ValueError, TypeError, OverflowError):
            raise ValueError('Informe latitude entre -90 e 90, longitude entre -180 e 180 e raio entre 0 e 100 km.')
        return lat, lon, km

    @staticmethod
    def distancia(lat1, lon1, lat2, lon2):
        a, b = math.radians(lat1), math.radians(lat2)
        hav = math.sin((b-a)/2)**2 + math.cos(a)*math.cos(b)*math.sin(math.radians(lon2-lon1)/2)**2
        return 2 * Proximidade.RAIO_TERRA * math.asin(math.sqrt(min(1, max(0, hav))))

    @staticmethod
    def prefixos(lat, lon, km):
        # A caixa esférica contém toda a circunferência, inclusive nos polos
        # e ao cruzar o antimeridiano. Células vizinhas nunca são omitidas.
        delta = km / Proximidade.RAIO_TERRA
        sul, norte = max(-90, lat-math.degrees(delta)), min(90, lat+math.degrees(delta))
        if sul <= -90 or norte >= 90:
            intervalos = [(-180, 180)]
        else:
            dl = math.degrees(math.asin(min(1, math.sin(delta)/math.cos(math.radians(lat)))))
            oeste, leste = lon-dl, lon+dl
            intervalos = ([(oeste+360, 180), (-180, leste)] if oeste <= -180 else
                          [(oeste, 180), (-180, leste-360)] if leste >= 180 else [(oeste, leste)])

        def celulas(precisao):
            nx, ny = 2**math.ceil(5*precisao/2), 2**math.floor(5*precisao/2)
            dx, dy = 360/nx, 180/ny
            # Margem numérica inclui coordenadas exatamente na fronteira.
            y0 = max(0, math.floor((sul+90)/dy-1e-10))
            y1 = min(ny-1, math.floor((norte+90)/dy+1e-10))
            ranges = [(max(0, math.floor((o+180)/dx-1e-10)),
                       min(nx-1, math.floor((l+180)/dx+1e-10))) for o,l in intervalos]
            return dx, dy, y0, y1, ranges

        precision = 1
        for candidate in range(2, 10):
            dx, dy, y0, y1, ranges = celulas(candidate)
            if (y1-y0+1)*sum(end-start+1 for start,end in ranges) > 64:
                break
            precision = candidate
        dx, dy, y0, y1, ranges = celulas(precision)
        return sorted({pygeohash.encode(-90+(y+.5)*dy, -180+(x+.5)*dx, precision=precision)
                       for y in range(y0,y1+1) for start,end in ranges for x in range(start,end+1)})

    @staticmethod
    def candidatos(db, lat, lon, km):
        # Somente o índice simples de geohash: sem índice composto por filtro.
        encontrados = {}
        for prefixo in Proximidade.prefixos(lat, lon, km):
            query = db.collection('trilhas').where(filter=FieldFilter('geohash', '>=', prefixo))
            query = query.where(filter=FieldFilter('geohash', '<=', prefixo+'\uf8ff'))
            for doc in query.stream():
                encontrados[doc.id] = doc
        return encontrados.values()
