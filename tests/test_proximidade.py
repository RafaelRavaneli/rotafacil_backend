import math
import unittest
import pygeohash
from services.proximidade import Proximidade
from services.trilhas import Trilhas
from services.indice_proximidade import atualizar_indice
from test_community import FakeDB, Query, Ref


class GeoQuery(Query):
    def where(self, field=None, op=None, value=None, *, filter=None):
        if filter is not None:
            field, op, value = filter.field_path, filter.op_string, filter.value
        return GeoQuery(self.db, self.path, (*self.filters, (field, op, value)))

    def stream(self):
        rows = [Ref(self.db, path).get() for path in self.db.data if path.rsplit('/',1)[0] == self.path]
        for field, op, value in self.filters:
            rows = [row for row in rows if row.data.get(field) is not None and
                    (row.data[field] >= value if op == '>=' else row.data[field] <= value if op == '<=' else row.data[field] == value)]
        return rows


class GeoDB(FakeDB):
    def collection(self, name):
        return GeoQuery(self, name)


class ProximityTests(unittest.TestCase):
    def test_gravacao_rejeita_coordenadas_invalidas_e_edicao_parcial_reindexa(self):
        db=GeoDB()
        db.collection('usuarios').document('g').set({'tipo':'guia','nome':'Guia'})
        user={'id':'g','tipo':'guia'}
        base={'nome':'Roteiro','descricao':'Descrição','dificuldade':'Iniciante','latitude':0,'longitude':0}
        for invalid in [True, float('nan'), float('inf'), 91]:
            self.assertEqual(Trilhas.cadastrar_trilha(db,{**base,'latitude':invalid},user)[1],400)
        result,status=Trilhas.cadastrar_trilha(db,base,user)
        self.assertEqual(status,201,result)
        id=result['id']
        result,status=Trilhas.atualizar_trilha(db,id,{'latitude':1},user)
        self.assertEqual(status,200,result)
        data=db.collection('trilhas').document(id).get().to_dict()
        self.assertEqual(data['geohash'],pygeohash.encode(1,0,precision=9))
        self.assertEqual(Trilhas.atualizar_trilha(db,id,{'longitude':181},user)[1],400)

    def test_indice_legado_seco_idempotente_sem_alterar_outros_dados(self):
        db=GeoDB()
        ref=db.collection('trilhas').document('legado')
        ref.set({'nome':'Legado','latitude':'0','longitude':'0','ativo':True})
        db.collection('trilhas').document('sem').set({'nome':'Sem coordenadas'})
        self.assertEqual(atualizar_indice(db)['pendentes'],1)
        self.assertNotIn('geohash',ref.get().to_dict())
        self.assertEqual(atualizar_indice(db,aplicar=True)['atualizados'],1)
        self.assertEqual(atualizar_indice(db,aplicar=True)['atualizados'],0)
        self.assertEqual(ref.get().to_dict()['nome'],'Legado')
        result,status=Trilhas.buscar_trilhas_avancado(db,{'latitude':0,'longitude':0,'raio_km':0,'pagina':1})
        self.assertEqual(status,200,result)
        self.assertEqual([t['id'] for t in result['itens']],['legado'])

    def test_periodo_considera_segunda_saida_e_empate_tem_ordem_estavel(self):
        db=GeoDB()
        for id in ['b','a']:
            self.add(db,id,0,0, datas=[{'data_hora_inicio':'2026-11-01T09:00:00','data_hora_fim':'2026-11-01T18:00:00'},
                                     {'data_hora_inicio':'2026-12-01T09:00:00','data_hora_fim':'2026-12-01T18:00:00'}])
        result,status=Trilhas.buscar_trilhas_avancado(db,{'latitude':0,'longitude':0,'raio_km':100,'pagina':1,'data_inicio':'2026-12-01','data_fim':'2026-12-01'})
        self.assertEqual(status,200,result)
        self.assertEqual([t['id'] for t in result['itens']],['a','b'])

    def add(self, db, id, lat, lon, **data):
        db.collection('trilhas').document(id).set({
            'nome': id, 'ativo': True, 'latitude': lat, 'longitude': lon,
            'geohash': pygeohash.encode(lat, lon, precision=9), **data})

    def test_validacao_zero_ausencia_limites_nan(self):
        self.assertEqual(Proximidade.validar(0, 0, 0), (0,0,0))
        for args in [(None,0,1),(0,None,1),(0,0,None),(91,0,10),(0,181,10),(0,0,-1),(0,0,101),('nan',0,10),(0,'inf',1),(True,0,10)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                Proximidade.validar(*args)
        db = GeoDB()
        self.assertEqual(Trilhas.buscar_trilhas_avancado(db, {'latitude': '0'})[1],400)

    def test_cobertura_fronteiras_polos_antimeridiano(self):
        for lat,lon,km in [(0,0,100),(-23.4,-51.9,100),(89.9,179.9,100),(-89.9,-179.9,100),(0,180,100),(0,0,0)]:
            prefixes = Proximidade.prefixos(lat,lon,km)
            self.assertLessEqual(len(prefixes),64)
            # Destinos em todos os azimutes na fronteira do raio.
            for bearing in range(0,360,5):
                a,b,d,t = math.radians(lat),math.radians(lon),km/6371,math.radians(bearing)
                y=math.asin(math.sin(a)*math.cos(d)+math.cos(a)*math.sin(d)*math.cos(t))
                x=b+math.atan2(math.sin(t)*math.sin(d)*math.cos(a),math.cos(d)-math.sin(a)*math.sin(y))
                point=pygeohash.encode(math.degrees(y),(math.degrees(x)+180)%360-180,precision=9)
                self.assertTrue(any(point.startswith(p) for p in prefixes),(lat,lon,km,bearing,point))

    def test_raio_paginacao_filtros_e_distancia_real(self):
        db=GeoDB()
        for i in range(65):
            self.add(db,f'r{i:02}',0,i/1000,estado='PR',cidade='Maringá',atividades=['Camping'],acessibilidade={'apoio_visual':True})
        self.add(db,'fora',0,2)
        self.add(db,'inativa',0,0,ativo=False)
        self.add(db,'suspensa',0,0,bloqueado_moderacao=True)
        filters={'latitude':'0','longitude':'0','raio_km':'100','pagina':'1','tamanho':'30','estado':'pr','modalidade':'Acampamento','recursos_acessibilidade':'apoio_visual'}
        ids=[]
        for page in (1,2,3):
            result,status=Trilhas.buscar_trilhas_avancado(db,{**filters,'pagina':str(page)})
            self.assertEqual(status,200,result)
            self.assertEqual(result['total'],65)
            ids.extend(t['id'] for t in result['itens'])
        self.assertEqual(ids,[f'r{i:02}' for i in range(65)])
        result,_=Trilhas.buscar_trilhas_avancado(db,{**filters,'raio_km':'0'})
        self.assertEqual([t['id'] for t in result['itens']],['r00'])
        self.assertEqual(result['itens'][0]['distancia_usuario_km'],0)
        result,_=Trilhas.buscar_trilhas_avancado(db,{**filters,'cidade':'inexistente'})
        self.assertEqual(result['itens'],[])

    def test_limite_100_km_e_celulas_vizinhas(self):
        db=GeoDB()
        for id,km in [('dentro',99.999),('fora',100.001),('vizinho',.001)]:
            self.add(db,id,0,-math.degrees(km/6371))
        result,status=Trilhas.buscar_trilhas_avancado(db,{'latitude':0,'longitude':0,'raio_km':100,'pagina':1})
        self.assertEqual(status,200,result)
        self.assertEqual([t['id'] for t in result['itens']],['vizinho','dentro'])
        self.assertAlmostEqual(result['itens'][1]['distancia_usuario_km'],99.999,places=6)
