import networkx as nx

class DependencyGraph:
    def __init__(self):
        self.graph = nx.DiGraph()

    def add_dependency(self, source, target, risk_level="MEDIUM"):
        self.graph.add_edge(source, target, risk=risk_level)

    def blockers(self, node):
        return list(self.graph.predecessors(node))

    def downstream_impact(self, node):
        return list(nx.descendants(self.graph, node))

    def critical_path(self):
        try:
            return nx.dag_longest_path(self.graph)
        except:
            return []