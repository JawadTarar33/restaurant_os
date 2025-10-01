import pandas as pd
from prophet import Prophet
from .models import Sales

def get_sales_dataframe(item_id=None, aggregate_daily=True):
    qs = Sales.objects.all()
    if item_id:
        qs = qs.filter(item_id=item_id)

    df = pd.DataFrame.from_records(qs.values("sale_date", "total_amount"))
    if df.empty:
        return df

    df.rename(columns={"sale_date": "ds", "total_amount": "y"}, inplace=True)
    df["ds"] = pd.to_datetime(df["ds"]).dt.tz_localize(None)

    if aggregate_daily:
        df = (
            df.groupby(df["ds"].dt.date)["y"]
              .sum()
              .reset_index()
              .rename(columns={"ds": "ds", "y": "y"})
        )
        df["ds"] = pd.to_datetime(df["ds"])  # convert back to datetime

    return df



def forecast_sales(item_id=None, periods=30):
    df = get_sales_dataframe(item_id=item_id)

    if df.empty:
        return None  # no data to forecast

    # Prophet needs 'ds' and 'y'
    model = Prophet()
    model.fit(df)

    future = model.make_future_dataframe(periods=periods)
    forecast = model.predict(future)

    # 🔑 Return the DataFrame, not a list
    return forecast

