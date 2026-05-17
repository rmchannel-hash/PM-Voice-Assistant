class PMReasoningEngine:

    def evaluate_migration_readiness(self, data):

        blockers = []

        if not data.get("wan_ready"):
            blockers.append("WAN readiness pending")

        if not data.get("cab_approved"):
            blockers.append("CAB approval missing")

        if not data.get("uat_signed"):
            blockers.append("UAT signoff pending")

        if blockers:
            return {
                "decision": "NO-GO",
                "blockers": blockers,
                "summary": "Migration cannot proceed"
            }

        return {
            "decision": "GO",
            "blockers": [],
            "summary": "Migration approved"
        }