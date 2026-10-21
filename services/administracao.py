"""Operações administrativas explícitas, com motivo e auditoria."""
import uuid
from datetime import datetime, timezone
from services.community import update_checked, CommunityError

class Administracao:
    @staticmethod
    def _admin(usuario):
        if usuario.get('tipo') != 'admin': raise CommunityError('Acesso administrativo obrigatório.',403)

    @staticmethod
    def _entrada(dados, acoes):
        if not isinstance(dados,dict) or set(dados) != {'acao','motivo'}:
            raise CommunityError('Informe somente ação e motivo.')
        acao=dados.get('acao'); motivo=dados.get('motivo')
        if not isinstance(acao,str) or acao not in acoes or not isinstance(motivo,str) or not 3 <= len(motivo.strip()) <= 500:
            raise CommunityError('Informe ação válida e motivo de 3 a 500 caracteres.')
        return acao,motivo.strip()

    @staticmethod
    def registrar(db,usuario,tipo,id_alvo,acao,motivo,estado_anterior=None,estado_novo=None):
        Administracao._admin(usuario)
        ref=db.collection('historico_admin').document(str(uuid.uuid4()))
        ref.create({'tipo':tipo,'id_alvo':id_alvo,'id_admin':usuario['id'],'acao':acao,'motivo':motivo,
                    'estado_anterior':estado_anterior or {},'estado_novo':estado_novo or {},
                    'criado_em':datetime.now(timezone.utc).isoformat(),'resultado':'solicitada'})
        return ref

    @staticmethod
    def _aplicar(db,usuario,tipo,doc,acao,motivo,mudancas):
        atual=doc.to_dict() or {}
        # Auditoria contém somente estados operacionais, nunca o perfil completo.
        audit=Administracao.registrar(db,usuario,tipo,doc.id,acao,motivo,
            {campo:atual.get(campo) for campo in mudancas},mudancas)
        try:
            update_checked(doc.reference,doc,mudancas)
        except CommunityError:
            audit.update({'resultado':'conflito'})
            raise
        audit.update({'resultado':'aplicada'})
        return {'mensagem':'Ação administrativa aplicada.'},200

    @staticmethod
    def contas(db,usuario,filtros):
        Administracao._admin(usuario)
        tipo=filtros.get('tipo','todos'); estado=filtros.get('estado','todos'); busca=filtros.get('q','').strip().casefold()
        if tipo not in {'todos','usuario','guia','agencia','admin'} or estado not in {'todos','ativas','bloqueadas','verificadas','nao_verificadas'} or len(busca)>120:
            raise CommunityError('Filtros inválidos.')
        result=[]
        campos=('nome','email','tipo','cidade','estado','cadastur_numero','cadastur_validade')
        for doc in db.collection('usuarios').stream():
            dados=doc.to_dict() or {}; ativa=dados.get('ativo') is not False; verificada=dados.get('verificado') is True
            if tipo!='todos' and dados.get('tipo')!=tipo: continue
            if estado=='ativas' and not ativa or estado=='bloqueadas' and ativa: continue
            if estado=='verificadas' and not verificada or estado=='nao_verificadas' and verificada: continue
            item={'id':doc.id,**{key:dados.get(key) for key in campos},'ativo':ativa,'verificado':verificada}
            if busca and not any(busca in str(item.get(key) or '').casefold() for key in ('nome','email','cidade','cadastur_numero')): continue
            result.append(item)
        return sorted(result,key=lambda item:str(item.get('nome') or '').casefold()),200

    @staticmethod
    def conta(db,usuario,id,dados):
        Administracao._admin(usuario)
        acao,motivo=Administracao._entrada(dados,{'bloquear','desbloquear','verificar','remover_verificacao'})
        doc=db.collection('usuarios').document(id).get()
        if not doc.exists: raise CommunityError('Conta não encontrada.',404)
        atual=doc.to_dict() or {}
        if atual.get('tipo')=='admin' or id==usuario['id']:
            raise CommunityError('Contas administrativas não podem ser alteradas por estas ações.',403)
        if acao in {'bloquear','desbloquear'}:
            ativo=acao=='desbloquear'
            if (atual.get('ativo') is not False)==ativo: raise CommunityError('A conta já está nessa situação.',409)
            mudancas={'ativo':ativo,'versao_auth':int(atual.get('versao_auth') or 0)+1}
        else:
            if atual.get('tipo') not in {'guia','agencia'}: raise CommunityError('Verificação disponível somente para guia/agência.')
            if acao=='verificar' and atual.get('ativo') is False: raise CommunityError('Desbloqueie a conta antes de verificar.',409)
            mudancas={'verificado':acao=='verificar','verificacao_suspensa_admin':acao=='remover_verificacao'}
        return Administracao._aplicar(db,usuario,'conta',doc,acao,motivo,mudancas)

    @staticmethod
    def roteiros(db,usuario,filtros):
        Administracao._admin(usuario)
        estado=filtros.get('estado','todos'); busca=filtros.get('q','').strip().casefold()
        if estado not in {'todos','ativos','inativos','suspensos','restritos'} or len(busca)>120: raise CommunityError('Filtros inválidos.')
        result=[]
        for doc in db.collection('trilhas').stream():
            dados=doc.to_dict() or {}; ativo=dados.get('ativo') is not False; suspenso=dados.get('bloqueado_moderacao') is True
            from services.trilhas import Trilhas
            responsavel_bloqueado=Trilhas._restricao_administrativa(db,{**dados,'bloqueado_moderacao':False})
            if estado=='restritos' and not responsavel_bloqueado: continue
            if estado=='ativos' and (not ativo or suspenso or responsavel_bloqueado) or estado=='inativos' and ativo or estado=='suspensos' and not suspenso: continue
            item={'id':doc.id,**{key:dados.get(key) for key in ('nome','cidade','estado','criado_por','id_guia')},'ativo':ativo,'bloqueado_moderacao':suspenso,'responsavel_bloqueado':responsavel_bloqueado}
            if busca and not any(busca in str(item.get(key) or '').casefold() for key in ('nome','cidade','criado_por')): continue
            result.append(item)
        return sorted(result,key=lambda item:str(item.get('nome') or '').casefold()),200

    @staticmethod
    def roteiro(db,usuario,id,dados):
        Administracao._admin(usuario)
        acao,motivo=Administracao._entrada(dados,{'suspender','liberar'})
        doc=db.collection('trilhas').document(id).get()
        if not doc.exists: raise CommunityError('Roteiro não encontrado.',404)
        suspender=acao=='suspender'
        if ((doc.to_dict() or {}).get('bloqueado_moderacao') is True)==suspender: raise CommunityError('O roteiro já está nessa situação.',409)
        return Administracao._aplicar(db,usuario,'roteiro',doc,acao,motivo,{'bloqueado_moderacao':suspender})

    @staticmethod
    def historico(db,usuario,filtros):
        Administracao._admin(usuario)
        tipo=filtros.get('tipo','todos'); id_alvo=filtros.get('id_alvo','').strip()
        if tipo not in {'todos','conta','roteiro','documento','avaliacao'} or len(id_alvo)>128: raise CommunityError('Filtros inválidos.')
        rows=[]
        for doc in db.collection('historico_admin').stream():
            value={**(doc.to_dict() or {}),'id':doc.id}
            if tipo!='todos' and value.get('tipo')!=tipo: continue
            if id_alvo and value.get('id_alvo')!=id_alvo: continue
            rows.append(value)
        if tipo in {'todos','avaliacao'}:
            for doc in db.collection('historico_moderacao_avaliacoes').stream():
                value=doc.to_dict() or {}
                if id_alvo and value.get('id_avaliacao')!=id_alvo: continue
                rows.append({**value,'id':doc.id,'tipo':'avaliacao','id_alvo':value.get('id_avaliacao')})
        return sorted(rows,key=lambda item:str(item.get('criado_em') or ''),reverse=True)[:500],200
