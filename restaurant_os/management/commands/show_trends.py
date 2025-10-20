# restaurant_os/management/commands/show_trends.py

from django.core.management.base import BaseCommand
from django.db.models import Avg, Sum
from restaurant_os.models import Branch, BranchDailySales
from datetime import timedelta
from django.utils import timezone


class Command(BaseCommand):
    help = 'Display sales trends and patterns for branches'

    def add_arguments(self, parser):
        parser.add_argument(
            '--branch-id',
            type=int,
            help='Show trends for specific branch only',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Number of days to analyze (default: 30)',
        )

    def handle(self, *args, **options):
        days = options['days']
        
        if options['branch_id']:
            branches = Branch.objects.filter(id=options['branch_id'], is_active=True)
        else:
            branches = Branch.objects.filter(is_active=True)

        if not branches.exists():
            self.stdout.write(self.style.ERROR('No branches found'))
            return

        self.stdout.write(self.style.SUCCESS(f'=== Sales Trends (Last {days} Days) ===\n'))

        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)

        for branch in branches:
            self.stdout.write(self.style.SUCCESS(f'\n📊 {branch.name} ({branch.city})'))
            self.stdout.write('─' * 60)

            # Get daily sales data
            daily_data = BranchDailySales.objects.filter(
                branch=branch,
                date__gte=start_date,
                date__lte=end_date
            ).order_by('date')

            if not daily_data.exists():
                self.stdout.write(self.style.WARNING('  No data available'))
                continue

            # Overall stats
            total_stats = daily_data.aggregate(
                total_revenue=Sum('revenue'),
                total_txns=Sum('transactions'),
                avg_revenue=Avg('revenue'),
                avg_txns=Avg('transactions'),
                avg_ticket=Avg('avg_ticket_size')
            )

            self.stdout.write(f'\n  Overall Performance:')
            self.stdout.write(f'    Total Revenue: PKR {float(total_stats["total_revenue"]):,.0f}')
            self.stdout.write(f'    Total Transactions: {total_stats["total_txns"]:,}')
            self.stdout.write(f'    Avg Daily Revenue: PKR {float(total_stats["avg_revenue"]):,.0f}')
            self.stdout.write(f'    Avg Daily Transactions: {float(total_stats["avg_txns"]):.1f}')
            self.stdout.write(f'    Avg Ticket Size: PKR {float(total_stats["avg_ticket"]):,.0f}')

            # Growth trend
            first_week = daily_data[:7].aggregate(avg=Avg('revenue'))
            last_week = daily_data[max(0, len(daily_data)-7):].aggregate(avg=Avg('revenue'))
            
            if first_week['avg'] and last_week['avg']:
                growth = ((last_week['avg'] - first_week['avg']) / first_week['avg'] * 100)
                trend_icon = '📈' if growth > 0 else '📉'
                color_func = self.style.SUCCESS if growth > 0 else self.style.WARNING
                
                self.stdout.write(color_func(
                    f'\n  {trend_icon} Trend: {growth:+.1f}% '
                    f'(First week: PKR {float(first_week["avg"]):,.0f} → '
                    f'Last week: PKR {float(last_week["avg"]):,.0f})'
                ))

            # Day of week analysis
            self.stdout.write(f'\n  Day of Week Performance:')
            day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            
            for day_num in range(7):
                day_sales = [d for d in daily_data if d.date.weekday() == day_num]
                if day_sales:
                    avg_txns = sum(d.transactions for d in day_sales) / len(day_sales)
                    avg_rev = sum(float(d.revenue) for d in day_sales) / len(day_sales)
                    
                    # Visual bar
                    max_txns = 80
                    bar_length = int((avg_txns / max_txns) * 20)
                    bar = '█' * bar_length + '░' * (20 - bar_length)
                    
                    self.stdout.write(
                        f'    {day_names[day_num][:3]}: {bar} '
                        f'{avg_txns:.0f} txns/day (PKR {avg_rev:,.0f})'
                    )

            # Recent 7 days detail
            self.stdout.write(f'\n  Last 7 Days:')
            recent = daily_data[max(0, len(daily_data)-7):]
            for day_data in recent:
                day_name = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][day_data.date.weekday()]
                self.stdout.write(
                    f'    {day_data.date} ({day_name}): '
                    f'{day_data.transactions} txns, '
                    f'PKR {float(day_data.revenue):,.0f}, '
                    f'Avg: PKR {float(day_data.avg_ticket_size):,.0f}'
                )

        self.stdout.write(self.style.SUCCESS('\n' + '═' * 60))


# restaurant_os/management/commands/quick_stats.py

from django.core.management.base import BaseCommand
from django.db.models import Count, Sum, Avg
from restaurant_os.models import *
from datetime import timedelta
from django.utils import timezone


class Command(BaseCommand):
    help = 'Quick statistical overview of the restaurant system'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('╔════════════════════════════════════════╗'))
        self.stdout.write(self.style.SUCCESS('║     Restaurant OS - Quick Stats        ║'))
        self.stdout.write(self.style.SUCCESS('╚════════════════════════════════════════╝\n'))

        # Today's stats
        today = timezone.now().date()
        
        today_sales = POSSale.objects.filter(created_at__date=today)
        if today_sales.exists():
            today_stats = today_sales.aggregate(
                revenue=Sum('total'),
                transactions=Count('id'),
                avg_ticket=Avg('total')
            )
            
            self.stdout.write('📅 Today\'s Performance:')
            self.stdout.write(f'   Revenue: PKR {float(today_stats["revenue"] or 0):,.0f}')
            self.stdout.write(f'   Transactions: {today_stats["transactions"]}')
            self.stdout.write(f'   Avg Ticket: PKR {float(today_stats["avg_ticket"] or 0):,.0f}\n')
        else:
            self.stdout.write(self.style.WARNING('📅 Today: No sales yet\n'))

        # This week
        week_ago = today - timedelta(days=7)
        week_sales = POSSale.objects.filter(created_at__date__gte=week_ago)
        
        if week_sales.exists():
            week_stats = week_sales.aggregate(
                revenue=Sum('total'),
                transactions=Count('id')
            )
            
            self.stdout.write('📆 This Week (Last 7 Days):')
            self.stdout.write(f'   Revenue: PKR {float(week_stats["revenue"]):,.0f}')
            self.stdout.write(f'   Transactions: {week_stats["transactions"]:,}')
            self.stdout.write(f'   Daily Avg: {week_stats["transactions"] / 7:.0f} transactions\n')

        # This month
        month_ago = today - timedelta(days=30)
        month_sales = POSSale.objects.filter(created_at__date__gte=month_ago)
        
        if month_sales.exists():
            month_stats = month_sales.aggregate(
                revenue=Sum('total'),
                transactions=Count('id')
            )
            
            self.stdout.write('📊 This Month (Last 30 Days):')
            self.stdout.write(f'   Revenue: PKR {float(month_stats["revenue"]):,.0f}')
            self.stdout.write(f'   Transactions: {month_stats["transactions"]:,}')
            self.stdout.write(f'   Daily Avg: {month_stats["transactions"] / 30:.0f} transactions\n')

        # Branch comparison
        self.stdout.write('🏪 Branch Rankings (Last 7 Days):')
        branches = Branch.objects.filter(is_active=True)
        
        branch_performance = []
        for branch in branches:
            stats = POSSale.objects.filter(
                branch=branch,
                created_at__date__gte=week_ago
            ).aggregate(
                revenue=Sum('total'),
                transactions=Count('id')
            )
            
            if stats['revenue']:
                branch_performance.append({
                    'name': branch.name,
                    'city': branch.city,
                    'revenue': float(stats['revenue']),
                    'transactions': stats['transactions']
                })
        
        branch_performance.sort(key=lambda x: x['revenue'], reverse=True)
        
        for i, bp in enumerate(branch_performance, 1):
            medal = ['🥇', '🥈', '🥉', '  '][min(i-1, 3)]
            self.stdout.write(
                f'   {medal} {i}. {bp["name"]:.<25} PKR {bp["revenue"]:>12,.0f} '
                f'({bp["transactions"]} txns)'
            )

        # Top selling items
        self.stdout.write('\n🌟 Top 5 Best Sellers (Last 7 Days):')
        top_items = POSSaleItem.objects.filter(
            sale__created_at__date__gte=week_ago
        ).values(
            'menu_item__name'
        ).annotate(
            total_qty=Sum('quantity'),
            total_revenue=Sum('total')
        ).order_by('-total_qty')[:5]
        
        for i, item in enumerate(top_items, 1):
            self.stdout.write(
                f'   {i}. {item["menu_item__name"]:.<30} '
                f'{item["total_qty"]} sold (PKR {float(item["total_revenue"]):,.0f})'
            )

        # Payment methods
        self.stdout.write('\n💳 Payment Methods (Last 7 Days):')
        payment_stats = POSSale.objects.filter(
            created_at__date__gte=week_ago
        ).values('payment_method').annotate(
            count=Count('id'),
            revenue=Sum('total')
        ).order_by('-count')
        
        total_txns = sum(p['count'] for p in payment_stats)
        
        for payment in payment_stats:
            pct = (payment['count'] / total_txns * 100) if total_txns > 0 else 0
            method_name = dict(POSSale.PAYMENT_METHODS).get(payment['payment_method'], payment['payment_method'])
            self.stdout.write(
                f'   {method_name:.<15} {payment["count"]:>4} txns ({pct:>5.1f}%) '
                f'- PKR {float(payment["revenue"]):>12,.0f}'
            )

        # Low stock alert
        low_stock_items = InventoryItem.objects.filter(
            quantity_in_stock__lte=models.F('reorder_level')
        ).count()
        
        if low_stock_items > 0:
            self.stdout.write(self.style.WARNING(
                f'\n⚠️  Alert: {low_stock_items} inventory items need reordering'
            ))

        # Customer insights
        returning_customers = POSSale.objects.filter(
            created_at__date__gte=week_ago,
            customer__isnull=False
        ).values('customer').annotate(
            visits=Count('id')
        ).filter(visits__gt=1).count()
        
        total_customers = POSSale.objects.filter(
            created_at__date__gte=week_ago,
            customer__isnull=False
        ).values('customer').distinct().count()
        
        if total_customers > 0:
            retention_rate = (returning_customers / total_customers * 100)
            self.stdout.write(f'\n👥 Customer Retention: {retention_rate:.1f}%')
            self.stdout.write(f'   {returning_customers} returning customers out of {total_customers} total')

        self.stdout.write(self.style.SUCCESS('\n' + '═' * 60))