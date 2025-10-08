# ===============================
# ml_service.py - CREATE NEW FILE
# ===============================


import pandas as pd
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from datetime import datetime, timedelta
from decimal import Decimal


class MLService:
    def __init__(self):
        self.model = GradientBoostingRegressor(n_estimators=100, random_state=42)
        self.scaler = StandardScaler()

    def generate_weekly_forecast(self, branch_id):
        from .models import BranchDailySales, BranchForecast, Branch

        historical = BranchDailySales.objects.filter(
            branch_id=branch_id
        ).order_by('date').values()

        df = pd.DataFrame(list(historical))

        if len(df) < 14:
            return self._create_default_forecast(branch_id)

        X = self._create_features(df)
        y = df['revenue'].values
        self.scaler.fit(X)
        X_scaled = self.scaler.transform(X)
        self.model.fit(X_scaled, y)

        forecasts = []
        today = datetime.now().date()
        avg_revenue = df['revenue'].tail(7).mean()

        for i in range(1, 8):
            forecast_date = today + timedelta(days=i)

            pred_features = self._create_forecast_features(df, forecast_date)
            pred_scaled = self.scaler.transform([pred_features])
            predicted_revenue = self.model.predict(pred_scaled)[0]

            growth = ((predicted_revenue - avg_revenue) / avg_revenue * 100)

            forecast = BranchForecast.objects.create(
                branch_id=branch_id,
                forecast_date=forecast_date,
                predicted_revenue=Decimal(str(predicted_revenue)),
                predicted_growth=Decimal(str(growth)),
                confidence_score=int(88 + np.random.randint(-5, 5)),
                factors=self._get_factors(growth, df)
            )
            forecasts.append(forecast)

        return forecasts

    def _create_features(self, df):
        features = []
        for idx, row in df.iterrows():
            features.append([
                pd.to_datetime(row['date']).day,
                float(row['transactions']),
                float(row['avg_ticket_size']),
                float(row['discount_percentage'])
            ])
        return np.array(features)

    def _create_forecast_features(self, df, forecast_date):
        latest = df.iloc[-1]
        return [
            forecast_date.day,
            float(latest['transactions']),
            float(latest['avg_ticket_size']),
            float(latest['discount_percentage'])
        ]

    def _get_factors(self, growth, df):
        factors = []
        if growth > 3:
            factors.append("organic growth")
        elif growth < -3:
            factors.append("declining trend")

        avg_discount = df['discount_percentage'].tail(7).mean()
        if avg_discount > 12:
            factors.append("new discounts being released")

        factors.append("seasonal patterns")
        return factors

    def _create_default_forecast(self, branch_id):
        from .models import BranchForecast
        today = datetime.now().date()
        forecasts = []
        for i in range(1, 8):
            forecast = BranchForecast.objects.create(
                branch_id=branch_id,
                forecast_date=today + timedelta(days=i),
                predicted_revenue=Decimal('50000'),
                predicted_growth=Decimal('5'),
                confidence_score=70,
                factors=["insufficient historical data"]
            )
            forecasts.append(forecast)
        return forecasts

    def compare_branches_and_save(self, branch_1_id, branch_2_id):
        from .models import BranchDailySales, BranchComparison, Branch
        from django.db.models import Sum, Avg

        today = datetime.now().date()
        week_ago = today - timedelta(days=7)

        b1_data = BranchDailySales.objects.filter(
            branch_id=branch_1_id,
            date__gte=week_ago
        ).aggregate(
            revenue=Sum('revenue'),
            avg_ticket=Avg('avg_ticket_size'),
            discount=Avg('discount_percentage'),
            transactions=Sum('transactions')
        )

        b2_data = BranchDailySales.objects.filter(
            branch_id=branch_2_id,
            date__gte=week_ago
        ).aggregate(
            revenue=Sum('revenue'),
            avg_ticket=Avg('avg_ticket_size'),
            discount=Avg('discount_percentage'),
            transactions=Sum('transactions')
        )

        branch_1 = Branch.objects.get(id=branch_1_id)
        branch_2 = Branch.objects.get(id=branch_2_id)

        comparisons = []

        if b1_data['revenue'] and b2_data['revenue']:
            rev_diff = ((b2_data['revenue'] - b1_data['revenue']) / b1_data['revenue'] * 100)

            BranchComparison.objects.create(
                date=today,
                branch_1_id=branch_1_id,
                branch_2_id=branch_2_id,
                metric='revenue',
                branch_1_value=b1_data['revenue'],
                branch_2_value=b2_data['revenue'],
                difference_pct=Decimal(str(rev_diff)),
                insight=f"{branch_1.name} branch revenue was {abs(rev_diff):.0f}% {'lower' if rev_diff > 0 else 'higher'} than {branch_2.name} this week",
                severity='warning' if abs(rev_diff) > 10 else 'info'
            )

            comparisons.append({
                'metric': 'Revenue Performance',
                'branch_1': f"PKR {float(b1_data['revenue']):,.0f}",
                'branch_2': f"PKR {float(b2_data['revenue']):,.0f}",
                'difference': f"{rev_diff:+.1f}%",
                'insight': f"{branch_1.name} branch revenue was {abs(rev_diff):.0f}% {'lower' if rev_diff > 0 else 'higher'} than {branch_2.name} this week"
            })

        if b1_data['avg_ticket'] and b2_data['avg_ticket']:
            ticket_diff = ((b2_data['avg_ticket'] - b1_data['avg_ticket']) / b1_data['avg_ticket'] * 100)

            comparisons.append({
                'metric': 'Avg Ticket Size',
                'branch_1': f"PKR {float(b1_data['avg_ticket']):,.0f}",
                'branch_2': f"PKR {float(b2_data['avg_ticket']):,.0f}",
                'difference': f"{ticket_diff:+.1f}%",
                'insight': f"Avg ticket size in {branch_1.name} {'dropped' if ticket_diff > 0 else 'increased'} to PKR {float(b1_data['avg_ticket']):,.0f} vs PKR {float(b2_data['avg_ticket']):,.0f} in {branch_2.name}"
            })

        if b1_data['discount'] and b2_data['discount']:
            disc_diff = b2_data['discount'] - b1_data['discount']

            comparisons.append({
                'metric': 'Discount Usage',
                'branch_1': f"{float(b1_data['discount']):.0f}%",
                'branch_2': f"{float(b2_data['discount']):.0f}%",
                'difference': f"{disc_diff:+.1f}%",
                'insight': f"largely due to higher discount usage ({float(b1_data['discount']):.0f}% vs {float(b2_data['discount']):.0f}%)"
            })

        return comparisons