class LifecycleAdvisor:

    def recommend(self, signals):

        infra = signals.get("infra_dependency", 0)
        compliance = signals.get("compliance", 0)
        volatility = signals.get("requirement_volatility", 0)
        procurement = signals.get("procurement", 0)
        innovation = signals.get("innovation", 0)

        if infra >= 8 and compliance >= 8:
            return {
                "methodology": "Predictive / Waterfall",
                "confidence": 92,
                "reason": "High governance and infrastructure dependency"
            }

        if volatility >= 8 and innovation >= 8:
            return {
                "methodology": "Agile Scrum",
                "confidence": 88,
                "reason": "Rapidly evolving requirements"
            }

        if infra >= 6 and volatility >= 5:
            return {
                "methodology": "Hybrid",
                "confidence": 90,
                "reason": "Infrastructure governance with evolving delivery"
            }

        return {
            "methodology": "Iterative",
            "confidence": 70,
            "reason": "Balanced delivery model"
        }