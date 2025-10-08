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
                'category': item.category.name if item.category else 'Other'
            })

        return Response(data)

    @action(detail=False, methods=['post'])
    def create_sale(self, request):
        serializer = CreatePOSSaleSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        data = serializer.validated_data
        branch_id = request.data.get('branch_id')

        if not branch_id:
            return Response({'error': 'branch_id required'}, status=400)

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
            'message': 'Sale created successfully'
        }, status=201)


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
