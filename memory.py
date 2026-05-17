from datetime import datetime

class OperationalMemory:
    def __init__(self):
        self.risks = []
        self.dependencies = []
        self.escalations = []
        self.stakeholders = []
        self.decisions = []
        self.lifecycle_recommendations = []
        self.change_requests = []
        self.cutover_readiness = []
        self.timeline_events = []

    def add(self, category, item):
        getattr(self, category).append({
            "timestamp": datetime.utcnow().isoformat(),
            "data": item
        })

    def get(self, category):
        return getattr(self, category, [])