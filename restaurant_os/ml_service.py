# ===============================
# ml_service.py - ENHANCED VERSION
# ===============================

import pandas as pd
import numpy as np
from prophet import Prophet
from prophet.diagnostics import cross_validation, performance_metrics
from sklearn.metrics import mean_absolute_percentage_error, mean_squared_error
from datetime import datetime, timedelta
from decimal import Decimal
import warnings
warnings.filterwarnings('ignore')


class MLService:
    def __init__(self):
        self.min_data_points = 14  # Minimum 2 weeks of data
        self.forecast_horizon = 7   # 1 week ahead
        
    def generate_weekly_forecast(self, branch_id):
        """
        Generate 7-day revenue forecast using Prophet with real confidence scores.
        This method always generates forecasts for the next 7 days from TODAY,
        and updates/replaces any existing forecasts for those dates.
        """
        from .models import BranchDailySales, BranchForecast, Branch

        today = datetime.now().date()
        
        # Delete old forecasts (past dates and existing future dates for this branch)
        # Keep forecasts fresh by removing outdated predictions
        BranchForecast.objects.filter(
            branch_id=branch_id,
            forecast_date__lte=today + timedelta(days=7)
        ).delete()

        # Fetch historical data (only actual past data, not forecasts)
        historical = BranchDailySales.objects.filter(
            branch_id=branch_id,
            date__lt=today  # Only past data
        ).order_by('date').values('date', 'revenue', 'transactions', 'discount_percentage')

        df = pd.DataFrame(list(historical))

        # Check if we have enough data
        if len(df) < self.min_data_points:
            return self._create_default_forecast(branch_id)

        # Prepare data for Prophet
        prophet_df = pd.DataFrame({
            'ds': pd.to_datetime(df['date']),
            'y': df['revenue'].astype(float)
        })

        try:
            # Train Prophet model with optimized parameters
            model = Prophet(
                changepoint_prior_scale=0.05,  # Flexibility of trend
                seasonality_prior_scale=10.0,   # Strength of seasonality
                seasonality_mode='multiplicative',
                daily_seasonality=False,
                weekly_seasonality=True,
                yearly_seasonality=False if len(df) < 365 else True
            )
            
            # Add custom regressors if enough data
            if len(df) >= 30:
                # Add discount as external regressor
                prophet_df['discount'] = df['discount_percentage'].astype(float)
                model.add_regressor('discount')
            
            model.fit(prophet_df)
            
            # Calculate confidence score based on model performance
            confidence_score = self._calculate_confidence_score(model, prophet_df)
            
            # Create future dataframe for next 7 days from TODAY
            future_dates = pd.DataFrame({
                'ds': pd.date_range(start=today + timedelta(days=1), periods=self.forecast_horizon)
            })
            
            # Add regressor values for future dates
            if len(df) >= 30:
                # Use average discount for future predictions
                avg_discount = df['discount_percentage'].tail(7).mean()
                future_dates['discount'] = avg_discount
            
            forecast = model.predict(future_dates)
            
            # Calculate growth factors
            avg_revenue_last_week = df['revenue'].tail(7).mean()
            
            forecasts = []
            
            for idx, row in forecast.iterrows():
                forecast_date = row['ds'].date()
                predicted_revenue = max(row['yhat'], 0)  # Ensure non-negative
                
                # Calculate growth percentage
                growth = ((predicted_revenue - avg_revenue_last_week) / avg_revenue_last_week * 100)
                
                # Get uncertainty intervals
                lower_bound = max(row['yhat_lower'], 0)
                upper_bound = row['yhat_upper']
                
                # Determine factors affecting forecast
                factors = self._analyze_forecast_factors(
                    df, 
                    growth, 
                    predicted_revenue, 
                    model,
                    forecast_date
                )
                
                # Use update_or_create to handle updates dynamically
                forecast_obj, created = BranchForecast.objects.update_or_create(
                    branch_id=branch_id,
                    forecast_date=forecast_date,
                    defaults={
                        'predicted_revenue': Decimal(str(round(predicted_revenue, 2))),
                        'predicted_growth': Decimal(str(round(growth, 2))),
                        'confidence_score': confidence_score,
                        'factors': factors
                    }
                )
                forecasts.append(forecast_obj)
            
            return forecasts
            
        except Exception as e:
            print(f"Prophet forecasting error: {str(e)}")
            return self._create_default_forecast(branch_id)

    def _calculate_confidence_score(self, model, df):
        """
        Calculate real confidence score based on model's historical accuracy
        """
        try:
            if len(df) < 21:  # Need at least 3 weeks for cross-validation
                return 70  # Conservative score for limited data
            
            # Perform cross-validation
            cv_results = cross_validation(
                model, 
                initial=f'{len(df) - 7} days',
                period='3 days',
                horizon='3 days',
                parallel="processes"
            )
            
            # Calculate performance metrics
            metrics = performance_metrics(cv_results)
            
            # Get MAPE (Mean Absolute Percentage Error)
            mape = metrics['mape'].mean()
            
            # Convert MAPE to confidence score (0-100)
            # Lower MAPE = Higher confidence
            # MAPE of 10% = 90 confidence, MAPE of 50% = 50 confidence
            confidence = max(0, min(100, 100 - (mape * 100)))
            
            return int(confidence)
            
        except Exception as e:
            print(f"Confidence calculation error: {str(e)}")
            # Fallback: Calculate simple accuracy on training data
            predictions = model.predict(df)
            mape = mean_absolute_percentage_error(df['y'], predictions['yhat'])
            confidence = max(0, min(100, 100 - (mape * 100)))
            return int(confidence)

    def _analyze_forecast_factors(self, df, growth, predicted_revenue, model, forecast_date):
        """
        Analyze what's driving the forecast using real data patterns
        """
        factors = []
        
        # 1. Growth trend analysis
        if growth > 5:
            factors.append("strong upward trend detected")
        elif growth > 0:
            factors.append("moderate growth expected")
        elif growth > -5:
            factors.append("slight decline anticipated")
        else:
            factors.append("significant decline expected")
        
        # 2. Seasonality analysis (day of week)
        day_of_week = forecast_date.weekday()
        df['day_of_week'] = pd.to_datetime(df['date']).dt.dayofweek
        
        # Calculate average revenue for this day of week
        same_day_avg = df[df['day_of_week'] == day_of_week]['revenue'].mean()
        overall_avg = df['revenue'].mean()
        
        if same_day_avg > overall_avg * 1.1:
            factors.append(f"historically strong {forecast_date.strftime('%A')}s")
        elif same_day_avg < overall_avg * 0.9:
            factors.append(f"typically slower {forecast_date.strftime('%A')}s")
        
        # 3. Recent trend analysis
        recent_7_days = df['revenue'].tail(7).mean()
        previous_7_days = df['revenue'].tail(14).head(7).mean() if len(df) >= 14 else recent_7_days
        
        recent_trend = ((recent_7_days - previous_7_days) / previous_7_days * 100) if previous_7_days > 0 else 0
        
        if recent_trend > 10:
            factors.append("recent momentum building")
        elif recent_trend < -10:
            factors.append("recent slowdown observed")
        
        # 4. Discount impact analysis
        avg_discount = df['discount_percentage'].tail(7).mean()
        if avg_discount > 15:
            factors.append("high discount activity")
        elif avg_discount > 10:
            factors.append("moderate promotional activity")
        
        # 5. Volatility analysis
        revenue_std = df['revenue'].tail(14).std()
        revenue_mean = df['revenue'].tail(14).mean()
        cv = (revenue_std / revenue_mean) if revenue_mean > 0 else 0
        
        if cv > 0.3:
            factors.append("high revenue volatility")
        
        return factors[:4]  # Return top 4 most relevant factors

    def _create_default_forecast(self, branch_id):
        """
        Create conservative forecast when insufficient data.
        Always creates forecasts for the next 7 days from TODAY.
        """
        from .models import BranchForecast, BranchDailySales
        
        today = datetime.now().date()
        
        # Delete old forecasts for this branch
        BranchForecast.objects.filter(
            branch_id=branch_id,
            forecast_date__lte=today + timedelta(days=7)
        ).delete()
        
        forecasts = []
        
        # Try to use whatever data we have
        recent_sales = BranchDailySales.objects.filter(
            branch_id=branch_id,
            date__lt=today  # Only past data
        ).order_by('-date')[:7]
        
        if recent_sales.exists():
            avg_revenue = sum(sale.revenue for sale in recent_sales) / len(recent_sales)
            base_revenue = float(avg_revenue)
        else:
            base_revenue = 50000  # Fallback default
        
        for i in range(1, 8):
            # Add slight random variation
            daily_revenue = base_revenue * (1 + np.random.uniform(-0.05, 0.05))
            
            forecast, created = BranchForecast.objects.update_or_create(
                branch_id=branch_id,
                forecast_date=today + timedelta(days=i),
                defaults={
                    'predicted_revenue': Decimal(str(round(daily_revenue, 2))),
                    'predicted_growth': Decimal('0.00'),
                    'confidence_score': 50,  # Low confidence due to insufficient data
                    'factors': ["insufficient historical data", "using baseline estimates"]
                }
            )
            forecasts.append(forecast)
        
        return forecasts

    def compare_branches_and_save(self, branch_1_id, branch_2_id):
        """
        Enhanced branch comparison with statistical analysis
        """
        from .models import BranchDailySales, BranchComparison, Branch
        from django.db.models import Sum, Avg
        from scipy import stats

        today = datetime.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)

        # Fetch data for both branches
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

        # Get branch objects
        branch_1 = Branch.objects.get(id=branch_1_id)
        branch_2 = Branch.objects.get(id=branch_2_id)

        comparisons = []

        # 1. Revenue Comparison with statistical significance
        if b1_data['revenue'] and b2_data['revenue']:
            rev_diff = ((b2_data['revenue'] - b1_data['revenue']) / b1_data['revenue'] * 100)
            
            # Determine severity based on magnitude
            if abs(rev_diff) > 20:
                severity = 'critical'
            elif abs(rev_diff) > 10:
                severity = 'warning'
            else:
                severity = 'info'

            insight = f"{branch_1.name} revenue is {abs(rev_diff):.1f}% {'lower' if rev_diff > 0 else 'higher'} than {branch_2.name} this week"
            
            BranchComparison.objects.create(
                date=today,
                branch_1_id=branch_1_id,
                branch_2_id=branch_2_id,
                metric='revenue',
                branch_1_value=b1_data['revenue'],
                branch_2_value=b2_data['revenue'],
                difference_pct=Decimal(str(round(rev_diff, 2))),
                insight=insight,
                severity=severity
            )

            comparisons.append({
                'metric': 'Revenue Performance',
                'branch_1': f"PKR {float(b1_data['revenue']):,.0f}",
                'branch_2': f"PKR {float(b2_data['revenue']):,.0f}",
                'difference': f"{rev_diff:+.1f}%",
                'insight': insight,
                'severity': severity
            })

        # 2. Transaction Volume Comparison
        if b1_data['transactions'] and b2_data['transactions']:
            trans_diff = ((b2_data['transactions'] - b1_data['transactions']) / b1_data['transactions'] * 100)
            
            comparisons.append({
                'metric': 'Transaction Volume',
                'branch_1': f"{b1_data['transactions']} orders",
                'branch_2': f"{b2_data['transactions']} orders",
                'difference': f"{trans_diff:+.1f}%",
                'insight': f"{branch_1.name} processed {abs(trans_diff):.1f}% {'fewer' if trans_diff > 0 else 'more'} transactions than {branch_2.name}"
            })

        # 3. Average Ticket Size Comparison
        if b1_data['avg_ticket'] and b2_data['avg_ticket']:
            ticket_diff = ((b2_data['avg_ticket'] - b1_data['avg_ticket']) / b1_data['avg_ticket'] * 100)

            comparisons.append({
                'metric': 'Avg Ticket Size',
                'branch_1': f"PKR {float(b1_data['avg_ticket']):,.0f}",
                'branch_2': f"PKR {float(b2_data['avg_ticket']):,.0f}",
                'difference': f"{ticket_diff:+.1f}%",
                'insight': f"Customers spend {abs(ticket_diff):.1f}% {'less' if ticket_diff < 0 else 'more'} per order at {branch_1.name}"
            })

        # 4. Discount Strategy Comparison
        if b1_data['discount'] and b2_data['discount']:
            disc_diff = b2_data['discount'] - b1_data['discount']

            comparisons.append({
                'metric': 'Discount Usage',
                'branch_1': f"{float(b1_data['discount']):.1f}%",
                'branch_2': f"{float(b2_data['discount']):.1f}%",
                'difference': f"{disc_diff:+.1f}%",
                'insight': f"{branch_1.name} using {abs(disc_diff):.1f}% {'less' if disc_diff < 0 else 'more'} discounts than {branch_2.name}"
            })

        # 5. Efficiency Metric (Revenue per Transaction)
        if b1_data['revenue'] and b1_data['transactions'] and b2_data['revenue'] and b2_data['transactions']:
            b1_efficiency = b1_data['revenue'] / b1_data['transactions']
            b2_efficiency = b2_data['revenue'] / b2_data['transactions']
            efficiency_diff = ((b2_efficiency - b1_efficiency) / b1_efficiency * 100)

            comparisons.append({
                'metric': 'Revenue Efficiency',
                'branch_1': f"PKR {float(b1_efficiency):,.0f}/order",
                'branch_2': f"PKR {float(b2_efficiency):,.0f}/order",
                'difference': f"{efficiency_diff:+.1f}%",
                'insight': f"{branch_2.name if efficiency_diff > 0 else branch_1.name} is more efficient at converting transactions to revenue"
            })

        return comparisons