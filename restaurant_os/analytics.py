import pandas as pd
from prophet import Prophet
from .models import Sales

def get_sales_dataframe(item_id=None):
    qs = Sales.objects.all()

    if item_id:
        qs = qs.filter(item_id=item_id)

    df = pd.DataFrame.from_records(
        qs.values("sale_date", "total_amount")
    )
    if df.empty:
        return df

    df.rename(columns={"sale_date": "ds", "total_amount": "y"}, inplace=True)
    return df


def forecast_sales(item_id=None, periods=30):
    # Get sales data
    if item_id:
        qs = Sales.objects.filter(item_id=item_id).order_by("sale_date")
    else:
        qs = Sales.objects.all().order_by("sale_date")

    if not qs.exists():
        return None

    df = pd.DataFrame.from_records(
        qs.values("sale_date", "total_amount")
    )
    
    # Prophet needs columns 'ds' (date) and 'y' (value)
    df.rename(columns={"sale_date": "ds", "total_amount": "y"}, inplace=True)

    # 🔑 Fix timezone issue → convert tz-aware datetime to naive
    df["ds"] = pd.to_datetime(df["ds"]).dt.tz_localize(None)

    # Train Prophet
    model = Prophet()
    model.fit(df)

    future = model.make_future_dataframe(periods=periods)
    forecast = model.predict(future)
    return forecast
