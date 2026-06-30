from plotly import graph_objs as go
from plotly.subplots import make_subplots
from plotly.offline import plot
from datetime import datetime, timezone


class Utils:
    @staticmethod
    def create_latest_aggregated_graph_as_html(device_id, latest_aggregated_data):
        if latest_aggregated_data is None:
            return None

        # construct data
        temp_x = []
        temp_y = []
        tds_x = []
        tds_y = []

        for data in latest_aggregated_data:
            if "temp" in data and data["temp"] != -1000:
                temp_x.append(data["yyyymmddhh"])
                temp_y.append(data["temp"])
            if "tds" in data and data["tds"] != -1000:
                tds_x.append(data["yyyymmddhh"])
                tds_y.append(data["tds"])

        fig = make_subplots(rows=1, cols=2)
        fig.update_layout(title=f"{device_id} latest aggregated data")

        # temp
        temp = go.Scatter(x=temp_x, y=temp_y, mode="lines+markers", name="temp")
        fig.add_trace(temp, row=1, col=1)

        # tds
        tds = go.Scatter(x=tds_x, y=tds_y, mode="lines+markers", name="tds")

        fig.add_trace(tds, row=1, col=2)

        # add layout h:480px
        fig.update_layout(height=480)

        return plot(fig, output_type="div")
