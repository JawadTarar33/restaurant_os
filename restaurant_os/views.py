# ===============================
# views.py - COMPLETE FILE
# ===============================

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth import authenticate
from rest_framework.authtoken.models import Token
from django.db.models import Sum, Avg, Count, F
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from .models import *
from .serializers import *
from .ml_service import MLService
from rest_framework.views import APIView
import requests
ml_service = MLService()


class AuthViewSet(viewsets.ViewSet):
    permission_classes = [AllowAny]

    @action(detail=False, methods=['post'])
    def login(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        
        user = User.objects.filter(email=email).first()
        if user and user.check_password(password):
            token, _ = Token.objects.get_or_create(user=user)
            return Response({
                'token': token.key,
                'user': UserSerializer(user).data
            })
        return Response({'error': 'Invalid credentials'}, status=400)

    @action(detail=False, methods=['post'])
    def register(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        full_name = request.data.get('full_name')
        role = request.data.get('role', 'staff')

        if User.objects.filter(email=email).exists():
            return Response({'error': 'User already exists'}, status=400)

        user = User.objects.create_user(
            email=email,
            password=password,
            full_name=full_name,
            role=role
        )

        token = Token.objects.create(user=user)
        return Response({
            'token': token.key,
            'user': UserSerializer(user).data
        }, status=201)


class RestaurantViewSet(viewsets.ModelViewSet):
    queryset = Restaurant.objects.all()
    serializer_class = RestaurantSerializer
    permission_classes = [IsAuthenticated]


class BranchViewSet(viewsets.ModelViewSet):
    queryset = Branch.objects.all()
    serializer_class = BranchSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=['get'])
    def weekly_summary(self, request, pk=None):
        branch = self.get_object()
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)

        summary = BranchDailySales.objects.filter(
            branch=branch,
            date__gte=week_ago
        ).aggregate(
            total_revenue=Sum('revenue'),
            total_transactions=Sum('transactions'),
            avg_ticket=Avg('avg_ticket_size')
        )

        return Response(summary)


class MenuItemViewSet(viewsets.ModelViewSet):
    queryset = MenuItem.objects.all()
    serializer_class = MenuItemSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        restaurant_id = self.request.query_params.get('restaurant_id')
        if restaurant_id:
            return self.queryset.filter(restaurant_id=restaurant_id, available=True)
        return self.queryset.filter(available=True)


class POSViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def menu_items(self, request):
        """Enhanced to include last_modified timestamp for sync"""
        restaurant_id = request.query_params.get('restaurant_id')

        items = MenuItem.objects.filter(available=True)
        if restaurant_id:
            items = items.filter(restaurant_id=restaurant_id)

        data = []
        for item in items:
            tax = item.price * Decimal('0.17')
            data.append({
                'id': item.id,
                'name': item.name,
                'price': float(item.price),
                'tax_rate': 17.00,
                'price_with_tax': float(item.price + tax),
                'category': item.category.name if item.category else 'Other',
                'last_modified': timezone.now().isoformat()  # For sync tracking
            })

        return Response({
            'items': data,
            'timestamp': timezone.now().isoformat()
        })

    @action(detail=False, methods=['post'])
    def create_sale(self, request):
        """Enhanced to handle both online and synced offline sales"""
        serializer = CreatePOSSaleSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        data = serializer.validated_data
        branch_id = request.data.get('branch_id')
        offline_id = request.data.get('offline_id')  # Track offline sales
        created_at = request.data.get('created_at')  # Original timestamp

        if not branch_id:
            return Response({'error': 'branch_id required'}, status=400)

        try:
            with db_transaction.atomic():
                customer, _ = Customer.objects.get_or_create(
                    contact=data['customer_contact'],
                    defaults={'name': data['customer_name']}
                )

                subtotal = Decimal('0')
                tax_total = Decimal('0')
                sale_items = []

                for item_data in data['items']:
                    menu_item = MenuItem.objects.get(id=item_data['menu_item_id'])
                    quantity = item_data['quantity']
                    unit_price = menu_item.price
                    item_subtotal = unit_price * quantity
                    item_tax = item_subtotal * Decimal('0.17')
                    item_total = item_subtotal + item_tax

                    subtotal += item_subtotal
                    tax_total += item_tax

                    sale_items.append({
                        'menu_item': menu_item,
                        'quantity': quantity,
                        'unit_price': unit_price,
                        'tax_amount': item_tax,
                        'total': item_total
                    })

                total = subtotal + tax_total - data['discount_amount']

                # Create sale with original timestamp if syncing from offline
                sale = POSSale.objects.create(
                    branch_id=branch_id,
                    customer=customer,
                    cashier=request.user,
                    payment_method=data['payment_method'],
                    subtotal=subtotal,
                    tax_amount=tax_total,
                    discount_amount=data['discount_amount'],
                    total=total
                )

                # If syncing offline sale, update created_at to original time
                if created_at:
                    sale.created_at = created_at
                    sale.save()

                for item in sale_items:
                    POSSaleItem.objects.create(
                        sale=sale,
                        menu_item=item['menu_item'],
                        quantity=item['quantity'],
                        unit_price=item['unit_price'],
                        tax_amount=item['tax_amount'],
                        total=item['total']
                    )

                return Response({
                    'sale_id': sale.id,
                    'total': float(total),
                    'offline_id': offline_id,  # Echo back for client tracking
                    'message': 'Sale created successfully',
                    'synced': True
                }, status=201)

        except Exception as e:
            return Response({
                'error': str(e),
                'offline_id': offline_id
            }, status=400)

    @action(detail=False, methods=['post'])
    def bulk_sync_sales(self, request):
        """Sync multiple offline sales at once"""
        sales_data = request.data.get('sales', [])
        
        if not sales_data:
            return Response({'error': 'No sales data provided'}, status=400)

        results = {
            'successful': [],
            'failed': []
        }

        for sale_data in sales_data:
            try:
                # Reuse create_sale logic
                response = self.create_sale(
                    type('Request', (), {
                        'data': sale_data,
                        'user': request.user
                    })()
                )
                
                if response.status_code == 201:
                    results['successful'].append({
                        'offline_id': sale_data.get('offline_id'),
                        'sale_id': response.data['sale_id']
                    })
                else:
                    results['failed'].append({
                        'offline_id': sale_data.get('offline_id'),
                        'error': response.data.get('error', 'Unknown error')
                    })
            except Exception as e:
                results['failed'].append({
                    'offline_id': sale_data.get('offline_id'),
                    'error': str(e)
                })

        return Response({
            'synced': len(results['successful']),
            'failed': len(results['failed']),
            'results': results
        })

    @action(detail=False, methods=['get'])
    def check_sync_status(self, request):
        """Check if there are any sales that need syncing"""
        offline_ids = request.query_params.get('offline_ids', '').split(',')
        
        if not offline_ids or offline_ids == ['']:
            return Response({'needs_sync': False})

        # Check which offline IDs are already synced
        # This would require adding an offline_id field to POSSale model
        # For now, return a simple status
        return Response({
            'needs_sync': True,
            'server_time': timezone.now().isoformat()
        })


# Add this new ViewSet for sync management
class SyncManagementViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'])
    def log_sync_event(self, request):
        """Log sync events for monitoring"""
        event_type = request.data.get('event_type')  # 'sync_start', 'sync_success', 'sync_failure'
        details = request.data.get('details', {})
        
        # You can create a SyncLog model to track these
        return Response({
            'logged': True,
            'timestamp': timezone.now().isoformat()
        })

    @action(detail=False, methods=['get'])
    def get_sync_stats(self, request):
        """Get sync statistics for a branch"""
        branch_id = request.query_params.get('branch_id')
        days = int(request.query_params.get('days', 7))
        
        start_date = timezone.now().date() - timedelta(days=days)
        
        # Get sales created in the specified period
        total_sales = POSSale.objects.filter(
            branch_id=branch_id,
            created_at__date__gte=start_date
        ).count()

        return Response({
            'total_sales': total_sales,
            'period_days': days,
            'branch_id': branch_id
        })


class FinanceDashboardViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def branch_overview(self, request):
        branch_id = request.query_params.get('branch_id')
        if not branch_id:
            return Response({'error': 'branch_id required'}, status=400)

        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)

        week_stats = POSSale.objects.filter(
            branch_id=branch_id,
            created_at__date__gte=week_ago
        ).aggregate(
            total_revenue=Sum('total'),
            total_transactions=Count('id'),
            avg_ticket=Avg('total'),
            total_tax=Sum('tax_amount'),
            total_discount=Sum('discount_amount')
        )

        month_stats = POSSale.objects.filter(
            branch_id=branch_id,
            created_at__date__gte=month_ago
        ).aggregate(
            revenue=Sum('total'),
            transactions=Count('id')
        )

        daily = []
        for i in range(7):
            date = today - timedelta(days=i)
            day_sales = POSSale.objects.filter(
                branch_id=branch_id,
                created_at__date=date
            ).aggregate(revenue=Sum('total'), count=Count('id'))

            daily.append({
                'date': str(date),
                'revenue': float(day_sales['revenue'] or 0),
                'transactions': day_sales['count']
            })

        return Response({
            'week': {
                'revenue': float(week_stats['total_revenue'] or 0),
                'transactions': week_stats['total_transactions'],
                'avg_ticket': float(week_stats['avg_ticket'] or 0),
                'tax_collected': float(week_stats['total_tax'] or 0),
                'discounts_given': float(week_stats['total_discount'] or 0)
            },
            'month': {
                'revenue': float(month_stats['revenue'] or 0),
                'transactions': month_stats['transactions']
            },
            'daily_breakdown': daily
        })

    @action(detail=False, methods=['get'])
    def all_branches(self, request):
        restaurant_id = request.query_params.get('restaurant_id')
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)

        branches = Branch.objects.filter(is_active=True)
        if restaurant_id:
            branches = branches.filter(restaurant_id=restaurant_id)

        data = []
        for branch in branches:
            stats = POSSale.objects.filter(
                branch=branch,
                created_at__date__gte=week_ago
            ).aggregate(
                revenue=Sum('total'),
                transactions=Count('id'),
                avg_ticket=Avg('total')
            )

            data.append({
                'branch_id': branch.id,
                'branch_name': branch.name,
                'city': branch.city,
                'revenue': float(stats['revenue'] or 0),
                'transactions': stats['transactions'],
                'avg_ticket': float(stats['avg_ticket'] or 0)
            })

        return Response(data)
    

    @action(detail=False, methods=['post'])
    def sync_daily_sales(self, request):
        """
        Admin-only endpoint to rebuild BranchDailySales from POSSale records.
        """
        if not request.user.is_superuser:
            return Response({'error': 'Permission denied'}, status=403)

        from django.db.models import Sum
        from decimal import Decimal
        from datetime import date
        import traceback

        try:
            branches = POSSale.objects.values_list('branch_id', flat=True).distinct()
            sale_dates = POSSale.objects.dates('created_at', 'day', order='DESC')

            total_created = 0
            for sale_date in sale_dates:
                for branch_id in branches:
                    daily_sales = POSSale.objects.filter(
                        branch_id=branch_id,
                        created_at__date=sale_date
                    )
                    if daily_sales.exists():
                        aggregates = daily_sales.aggregate(
                            total_revenue=Sum('total'),
                            total_discount=Sum('discount_amount')
                        )

                        total_revenue = aggregates['total_revenue'] or Decimal('0')
                        total_discount = aggregates['total_discount'] or Decimal('0')
                        total_transactions = daily_sales.count()
                        avg_ticket = (total_revenue / total_transactions) if total_transactions > 0 else Decimal('0')
                        discount_pct = (total_discount / total_revenue * 100) if total_revenue > 0 else Decimal('0')

                        BranchDailySales.objects.update_or_create(
                            branch_id=branch_id,
                            date=sale_date,
                            defaults={
                                'revenue': total_revenue,
                                'transactions': total_transactions,
                                'customer_footfall': int(total_transactions * Decimal('1.2')),
                                'avg_ticket_size': avg_ticket,
                                'discount_percentage': discount_pct
                            }
                        )
                        total_created += 1

            return Response({'message': f'Successfully synced {total_created} BranchDailySales records.'})

        except Exception as e:
            print(traceback.format_exc())
            return Response({'error': str(e)}, status=500)
        


    @action(detail=False, methods=['post'])
    def sync_orders(self, request):
        if not request.user.is_superuser:
            return Response({'error': 'Permission denied'}, status=403)

        total_created = 0
        for sale in POSSale.objects.all():
            order, created = Order.objects.get_or_create(
                sale=sale,
                defaults={
                    'customer': sale.customer,
                    'branch': sale.branch,
                    'total_amount': sale.total,
                    'payment_method': sale.payment_method,
                    'created_at': sale.created_at
                }
            )
            if created:
                total_created += 1

        return Response({'message': f'Successfully synced {total_created} Orders.'})


class SalesAnalyticsViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def branch_sales(self, request):
        branch_id = request.query_params.get('branch_id')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        query = BranchDailySales.objects.all()
        if branch_id:
            query = query.filter(branch_id=branch_id)
        if start_date and end_date:
            query = query.filter(date__range=[start_date, end_date])

        serializer = BranchDailySalesSerializer(query, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def all_branches_sales(self, request):
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)

        branches = Branch.objects.filter(is_active=True)
        data = []

        for branch in branches:
            sales = BranchDailySales.objects.filter(
                branch=branch,
                date__gte=week_ago
            ).aggregate(
                revenue=Sum('revenue'),
                transactions=Sum('transactions'),
                avg_ticket=Avg('avg_ticket_size'),
                discount_pct=Avg('discount_percentage')
            )

            data.append({
                'branch_id': branch.id,
                'branch_name': branch.name,
                'revenue': float(sales['revenue'] or 0),
                'transactions': sales['transactions'] or 0,
                'avg_ticket': float(sales['avg_ticket'] or 0),
                'discount_usage': float(sales['discount_pct'] or 0)
            })

        return Response(data)


class AIForecastViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'])
    def generate_forecast(self, request):
        branch_id = request.data.get('branch_id')

        if not branch_id:
            return Response({'error': 'branch_id required'}, status=400)

        try:
            forecasts = ml_service.generate_weekly_forecast(branch_id)
            serializer = BranchForecastSerializer(forecasts, many=True)
            return Response(serializer.data)
        except Exception as e:
            return Response({'error': str(e)}, status=500)

    @action(detail=False, methods=['get'])
    def all_branches_forecast(self, request):
        restaurant_id = request.query_params.get('restaurant_id')

        branches = Branch.objects.filter(is_active=True)
        if restaurant_id:
            branches = branches.filter(restaurant_id=restaurant_id)

        results = []
        today = timezone.now().date()

        for branch in branches:
            latest = BranchForecast.objects.filter(
                branch=branch,
                forecast_date__gte=today
            ).first()

            if latest:
                results.append({
                    'branch_id': branch.id,
                    'branch_name': branch.name,
                    'city': branch.city,
                    'predicted_growth': float(latest.predicted_growth),
                    'confidence': latest.confidence_score,
                    'factors': latest.factors,
                    'predicted_revenue': float(latest.predicted_revenue),
                    'message': f"The model has predicted that {branch.name} branch will sell {abs(float(latest.predicted_growth)):.1f}% {'more' if latest.predicted_growth > 0 else 'less'} next week as we are expecting {', '.join(latest.factors[:2])}"
                })

        return Response(results)


class AIComparisonViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'])
    def compare_branches(self, request):
        branch_1_id = request.data.get('branch_1_id')
        branch_2_id = request.data.get('branch_2_id')

        if not branch_1_id or not branch_2_id:
            return Response({'error': 'Both branch IDs required'}, status=400)

        try:
            comparisons = ml_service.compare_branches_and_save(branch_1_id, branch_2_id)
            return Response(comparisons)
        except Exception as e:
            return Response({'error': str(e)}, status=500)

    @action(detail=False, methods=['get'])
    def latest_comparisons(self, request):
        today = timezone.now().date()
        comparisons = BranchComparison.objects.filter(date=today)[:10]
        serializer = BranchComparisonSerializer(comparisons, many=True)
        return Response(serializer.data)


class InventoryViewSet(viewsets.ModelViewSet):
    queryset = InventoryItem.objects.all()
    serializer_class = InventoryItemSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def low_stock(self, request):
        restaurant_id = request.query_params.get('restaurant_id')
        query = self.queryset.filter(quantity_in_stock__lte=F('reorder_level'))
        if restaurant_id:
            query = query.filter(restaurant_id=restaurant_id)

        serializer = self.get_serializer(query, many=True)
        return Response(serializer.data)


class SupplierViewSet(viewsets.ModelViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [IsAuthenticated]


class InventoryOrderViewSet(viewsets.ModelViewSet):
    queryset = InventoryOrder.objects.all()
    serializer_class = InventoryOrderSerializer
    permission_classes = [IsAuthenticated]


class AskAIView(APIView):
    """
    Main entry point for AI chat functionality.
    Forwards user queries to n8n workflow and returns AI responses.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user_message = request.data.get("message")
        branch_id = request.data.get("branch_id")
        restaurant_id = request.data.get("restaurant_id")
        
        if not user_message:
            return Response(
                {"error": "message field is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Prepare payload for n8n
        payload = {
            "user_id": request.user.id,
            "user_email": request.user.email,
            "user_role": request.user.role,
            "query": user_message,
            "branch_id": branch_id,
            "restaurant_id": restaurant_id,
            "context": {
                "user_name": request.user.full_name or request.user.email,
                "timestamp": timezone.now().isoformat()
            }
        }

        try:
            # Forward to n8n webhook
            response = requests.post(
                settings.N8N_WEBHOOK_URL,
                json=payload,
                headers={
                    'X-API-Key': settings.N8N_API_KEY,  # Optional security header
                    'Content-Type': 'application/json'
                },
                timeout=120  # 2 minute timeout for complex queries
            )
            
            response.raise_for_status()
            return Response(response.json(), status=response.status_code)
            
        except requests.exceptions.Timeout:
            return Response(
                {"error": "Request timed out. Please try again."},
                status=status.HTTP_504_GATEWAY_TIMEOUT
            )
        except requests.exceptions.RequestException as e:
            return Response(
                {"error": f"Failed to connect to AI service: {str(e)}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class RunModelView(APIView):
    """
    Endpoint for n8n to call ML models hosted in Django.
    This allows n8n workflows to leverage your sklearn models.
    """
    permission_classes = [AllowAny]  # Or use API key authentication

    def post(self, request):
        # Verify API key from n8n
        api_key = request.headers.get('X-API-Key')
        if api_key != settings.N8N_API_KEY:
            return Response(
                {"error": "Unauthorized"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        model_type = request.data.get("model_type")
        branch_id = request.data.get("branch_id")
        features = request.data.get("features")

        if not model_type or not branch_id:
            return Response(
                {"error": "model_type and branch_id are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            if model_type == "forecast":
                forecasts = ml_service.generate_weekly_forecast(branch_id)
                return Response({
                    "status": "success",
                    "model_type": "forecast",
                    "results": BranchForecastSerializer(forecasts, many=True).data
                })

            elif model_type == "comparison":
                branch_2_id = request.data.get("branch_2_id")
                if not branch_2_id:
                    return Response(
                        {"error": "branch_2_id required for comparison"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                comparisons = ml_service.compare_branches_and_save(branch_id, branch_2_id)
                return Response({
                    "status": "success",
                    "model_type": "comparison",
                    "results": comparisons
                })

            elif model_type == "sales_prediction":
                # Example: Custom prediction using features
                from joblib import load
                import numpy as np
                
                # Load your trained model
                # model = load("models/sales_forecast.joblib")
                # prediction = model.predict([features])
                
                return Response({
                    "status": "success",
                    "model_type": "sales_prediction",
                    "prediction": "Implementation depends on your model"
                })

            else:
                return Response(
                    {"error": f"Unknown model_type: {model_type}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ChatHistoryView(APIView):
    """
    Optional: Store and retrieve chat history
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Implement chat history retrieval
        # You might want to create a ChatMessage model
        return Response({
            "history": [],
            "message": "Chat history endpoint - implement based on your needs"
        })

    def post(self, request):
        # Store chat message
        return Response({"status": "saved"})