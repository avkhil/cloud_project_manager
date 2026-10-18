from datetime import datetime
from threading import Lock
from app import db
from app.models import Process, ResourceEvent

# OS simulation: Round Robin queue + counting semaphore (3 concurrent workers).
class ProcessManager:
    def __init__(self, capacity=3, quantum=2):
        self.capacity = capacity
        self.quantum = quantum
        self.active = 0
        self.lock = Lock()

    def create(self, user_id, operation, burst_time=3, priority=5):
        with self.lock:
            pid = f'P{int(datetime.utcnow().timestamp() * 1000) % 1000000}'
            p = Process(pid=pid, user_id=user_id, operation=operation, burst_time=burst_time,
                        remaining_time=burst_time, priority=priority, state='READY')
            db.session.add(p)
            db.session.commit()
            return p

    def run(self, process):
        with self.lock:
            if self.active >= self.capacity:
                process.state = 'WAITING'
                db.session.add(ResourceEvent(process_id=process.id, resource_name='BACKUP_WORKER', event_type='WAITING'))
                db.session.commit()
                return process
            self.active += 1
            process.state = 'RUNNING'
            process.started_at = datetime.utcnow()
            db.session.add(ResourceEvent(process_id=process.id, resource_name='BACKUP_WORKER', event_type='ALLOCATED'))
            db.session.commit()
            return process

    def finish(self, process):
        with self.lock:
            process.remaining_time = 0
            process.state = 'TERMINATED'
            process.completed_at = datetime.utcnow()
            db.session.add(ResourceEvent(process_id=process.id, resource_name='BACKUP_WORKER', event_type='RELEASED'))
            self.active = max(0, self.active - 1)
            db.session.commit()

process_manager = ProcessManager()
