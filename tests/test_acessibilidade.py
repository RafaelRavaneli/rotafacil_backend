import unittest
from services.acessibilidade import Acessibilidade
from services.trilhas import Trilhas
from test_community import FakeDB, Query

class FilterQuery(Query):
    def where(self, field=None, op=None, value=None, *, filter=None):
        if filter is not None:
            field, op, value = filter.field_path, filter.op_string, filter.value
        return FilterQuery(self.db, self.path, (*self.filters, (field, op, value)))

class FilterDB(FakeDB):
    def collection(self, name):
        return FilterQuery(self, name)

class AccessibilityTests(unittest.TestCase):
    def test_validacao_nao_confunde_ausencia_nao_e_sim(self):
        self.assertEqual(Acessibilidade.validar({}), {})
        self.assertEqual(Acessibilidade.validar({'apoio_visual': None}), {'apoio_visual': None})
        self.assertEqual(Acessibilidade.validar({'apoio_visual': False}), {'apoio_visual': False})
        for bad in (None, [], {'extra': True}, {'apoio_visual': 'sim'}, {'idade_minima': True}, {'idade_minima': -1}, {'idade_minima': 121}, {'idade_minima': 1.5}, {'adaptacoes': 'x'*1501}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                Acessibilidade.validar(bad)
        self.assertEqual(Acessibilidade.validar({'adaptacoes': ' Apoio ', 'idade_minima': 0}), {'adaptacoes': 'Apoio', 'idade_minima': 0})

    def test_criacao_edicao_consulta_preservam_contrato_e_legado(self):
        db = FakeDB()
        user = {'id': 'g', 'tipo': 'guia'}
        db.collection('usuarios').document('g').set({'nome': 'Guia', 'tipo': 'guia'})
        base = {'nome': 'Roteiro', 'descricao': 'Descrição', 'dificuldade': 'Iniciante'}
        result, status = Trilhas.cadastrar_trilha(db, {**base, 'acessibilidade': {'apoio_visual': True, 'idade_minima': 12}}, user)
        self.assertEqual(status, 201, result)
        id = result['id']
        self.assertEqual(Trilhas.buscar_trilha_por_id(db,id)[0]['acessibilidade']['idade_minima'], 12)
        self.assertEqual(Trilhas.atualizar_trilha(db,id,{'acessibilidade': {'apoio_visual': False}},user)[1],200)
        self.assertEqual(Trilhas.buscar_trilha_por_id(db,id)[0]['acessibilidade'], {'apoio_visual': False})
        self.assertEqual(Trilhas.atualizar_trilha(db,id,{'acessibilidade': {'idade_minima': -1}},user)[1],400)
        self.assertEqual(Trilhas.cadastrar_trilha(db,base,user)[1],201)

    def test_filtros_exigem_todos_recursos_e_nao_prometem_legado(self):
        db = FilterDB()
        for id, info in [('legado', None), ('sim', {'apoio_visual': True, 'banheiro_acessivel': True}), ('parcial', {'apoio_visual': True}), ('nao', {'apoio_visual': False})]:
            value={'nome': id, 'ativo': True}
            if info is not None: value['acessibilidade']=info
            db.collection('trilhas').document(id).set(value)
        results,status=Trilhas.buscar_trilhas_avancado(db, {'recursos_acessibilidade':'apoio_visual,banheiro_acessivel'})
        self.assertEqual(status,200,results)
        self.assertEqual([x['id'] for x in results],['sim'])
        self.assertEqual(len(Trilhas.buscar_trilhas_avancado(db,{})[0]),4)
        self.assertEqual(Trilhas.buscar_trilhas_avancado(db,{'recursos_acessibilidade':'senha'})[1],400)
