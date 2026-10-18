from flask import Blueprint, request, jsonify
from app import db
from app.models import Folder
from app.routes.common import auth_required

folders_bp=Blueprint('folders',__name__)

@folders_bp.get('')
@auth_required
def list_folders(user):
    return jsonify({'folders':[{'id':f.id,'name':f.name,'parent_id':f.parent_id,'created_at':f.created_at.isoformat()} for f in Folder.query.filter_by(user_id=user.id).order_by(Folder.name).all()]})

@folders_bp.post('')
@auth_required
def create_folder(user):
    data=request.get_json() or {}; name=data.get('name','').strip(); parent_id=data.get('parent_id')
    if not name: return jsonify({'error':'Folder name required'}),400
    if Folder.query.filter_by(user_id=user.id,parent_id=parent_id,name=name).first(): return jsonify({'error':'Folder already exists'}),409
    f=Folder(user_id=user.id,parent_id=parent_id,name=name); db.session.add(f); db.session.commit()
    return jsonify({'id':f.id,'name':f.name,'parent_id':f.parent_id}),201
