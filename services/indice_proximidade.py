"""Atualização idempotente de geohash legado; nenhuma execução automática."""
import pygeohash
from services.proximidade import Proximidade
from services.community import update_checked, CommunityError


def atualizar_indice(db, aplicar=False):
    resumo = {'corretos': 0, 'pendentes': 0, 'atualizados': 0, 'sem_coordenadas_validas': 0, 'conflitos': 0}
    for doc in db.collection('trilhas').stream():
        dados = doc.to_dict() or {}
        try:
            lat, lon, _ = Proximidade.validar(dados.get('latitude'), dados.get('longitude'), 0)
        except ValueError:
            resumo['sem_coordenadas_validas'] += 1
            continue
        geohash = pygeohash.encode(lat, lon, precision=9)
        if dados.get('geohash') == geohash:
            resumo['corretos'] += 1
            continue
        resumo['pendentes'] += 1
        if aplicar:
            try:
                update_checked(doc.reference, doc, {'geohash': geohash, 'latitude': lat, 'longitude': lon})
                resumo['atualizados'] += 1
            except CommunityError:
                resumo['conflitos'] += 1
    return resumo
