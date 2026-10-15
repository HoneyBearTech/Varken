class Outputs(object):
    """Where the points each job collects go: InfluxDB, the Prometheus collector, or both.

    The service modules only call write_points, so they don't need to know which outputs are on.
    """

    def __init__(self, influx=None, metrics=None):
        self.influx = influx
        self.metrics = metrics

    def write_points(self, points):
        if self.metrics:
            self.metrics.observe(points)
        if self.influx:
            self.influx.write_points(points)
