from app import create_app, db
from app.models import User
from app.services.auth import hash_password

app=create_app()
with app.app_context():
    db.create_all()
    if not User.query.filter_by(email='admin@cloud.local').first():
        db.session.add(User(name='System Admin',email='admin@cloud.local',password_hash=hash_password('admin123'),role='ADMIN'))
    if not User.query.filter_by(email='user@cloud.local').first():
        db.session.add(User(name='Demo User',email='user@cloud.local',password_hash=hash_password('user123'),role='MEMBER'))
    db.session.commit()
    print('Seed complete: admin@cloud.local / admin123 and user@cloud.local / user123')
