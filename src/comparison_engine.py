from dataclasses import dataclass
from typing import List, Optional, Tuple
from tariff import Tariff
import config
from datetime import date
from account_info import AccountInfo
from query_service import QueryService
import logging
logger = logging.getLogger('octobot.comparison_engine')
@dataclass
class CostBreakdown:
    """Breakdown of electricity costs."""
    consumption_cost: float  # in pence
    standing_charge: float   # in pence
    total_cost: float       # in pence
    total_kwh: float

    @property
    def total_cost_pounds(self) -> float:
        return self.total_cost / 100

    @property
    def consumption_cost_pounds(self) -> float:
        return self.consumption_cost / 100

    @property
    def standing_charge_pounds(self) -> float:
        return self.standing_charge / 100

@dataclass
class TariffComparison:
    """Result of comparing a single tariff."""
    tariff: Tariff
    cost_breakdown: Optional[CostBreakdown]
    error: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return self.error is None and self.cost_breakdown is not None

    @property
    def total_cost(self) -> Optional[float]:
        return self.cost_breakdown.total_cost if self.cost_breakdown else None

@dataclass
class ComparisonResult:
    current_tariff_comparison: TariffComparison
    alternative_comparisons: List[TariffComparison]
    cheapest_tariff: Optional[Tariff]
    potential_savings: float  # in pence

    @property
    def should_switch(self) -> bool:
        return (self.cheapest_tariff is not None and
                self.cheapest_tariff != self.current_tariff_comparison.tariff and
                self.potential_savings > config.SWITCH_THRESHOLD) # buffer

    @property
    def all_comparisons(self) -> List[TariffComparison]:
        return [self.current_tariff_comparison] + self.alternative_comparisons


class ComparisonEngine:
    def __init__(self, query_service: QueryService):
        logger.debug(f"Initialising {__class__.__name__}")
        self.query_service = query_service

    def compare_tariffs(self,
                        account_info: AccountInfo,
                        available_tariffs: List[Tariff]) -> ComparisonResult:

        curr_costs = self._calculate_current_cost(account_info)
        curr_comparison = TariffComparison(tariff=account_info.current_tariff, cost_breakdown=curr_costs)
        #gets a list of tariffs
        alternative_comparisons = []
        for tariff in available_tariffs:
            if tariff == account_info.current_tariff:
                continue
            comparison = self._compare_tariff(tariff, account_info)
            alternative_comparisons.append(comparison)

        logger.debug(f"Tariff comparison results - {alternative_comparisons}")
        cheapest_tariff, potential_savings = self._find_best_option(
            curr_comparison,
            alternative_comparisons
        )

        return ComparisonResult(
            current_tariff_comparison=curr_comparison,
            alternative_comparisons=alternative_comparisons,
            cheapest_tariff=cheapest_tariff,
            potential_savings=potential_savings
        )

    def _find_best_option(self,
                          current: TariffComparison,
                          alternatives: List[TariffComparison]
                          ) -> Tuple[Optional[Tariff], float]:
        """Find the cheapest tariff option among all switchable tariffs."""
        # Get all valid comparisons for switchable tariffs
        valid_comparisons = [current] if current.tariff.switchable else []
        valid_comparisons.extend([
            comp for comp in alternatives
            if comp.is_valid and comp.tariff.switchable
        ])

        if not valid_comparisons:
            return None, 0.0

        # Find cheapest
        cheapest = min(valid_comparisons, key=lambda x: x.total_cost)

        # Calculate savings
        current_cost = current.total_cost if current.is_valid else float('inf')
        cheapest_cost = cheapest.total_cost if cheapest.is_valid else float('inf')
        savings = current_cost - cheapest_cost

        return cheapest.tariff, savings

    def _compare_tariff(self, tariff: Tariff, account_info: AccountInfo) -> TariffComparison:
        """
        Compare tariff against today's usage
        """
        standing_charge, unit_rates, product_code = self._get_potential_tariff_rates(
            tariff,
            account_info.region_code
        )

        # Store product code for potential switching
        tariff.product_code = product_code

        # Calculate costs based on consumption
        period_costs = self._calculate_potential_costs(
            account_info.consumption,
            unit_rates
        )

        # Sum up costs
        consumption_cost = sum(period['calculated_cost'] for period in period_costs)
        total_cost = consumption_cost + standing_charge

        # Get total kWh (same as current consumption)
        total_wh = sum(
            float(entry.get('consumptionDelta', 0)) 
            for entry in account_info.consumption
        )
        total_kwh = total_wh / 1000

        cost_breakdown = CostBreakdown(
            consumption_cost=consumption_cost,
            standing_charge=standing_charge,
            total_cost=total_cost,
            total_kwh=total_kwh
        )

        return TariffComparison(tariff=tariff, cost_breakdown=cost_breakdown)


    def _calculate_current_cost(self, account_info:AccountInfo) -> CostBreakdown:
        # Total consumption cost -remove comment
        total_con_cost = sum(float(entry['costDeltaWithTax'] or 0) for entry in account_info.consumption)

            # Total consumption
        total_wh = sum(float(consumption['consumptionDelta']) for consumption in account_info.consumption)
        total_kwh = total_wh / 1000

        return CostBreakdown(
                consumption_cost=total_con_cost,
                standing_charge=account_info.standing_charge,
                total_cost=total_con_cost + account_info.standing_charge,
                total_kwh=total_kwh
            )

    def _calculate_potential_costs(self,
                                   consumption_data: List[dict],
                                   rate_data: List[dict]) -> List[dict]:

        period_costs = []
        for consumption in consumption_data:
            read_time = consumption['readAt'].replace('+00:00', 'Z')
            matching_rate = next(
                rate for rate in rate_data
                # Flexible has no end time, so default to the end of time
                if rate['valid_from'] <= read_time <= (rate.get('valid_to') or "9999-12-31T23:59:59Z")
                # DIRECT_DEBIT is for flexible that has different price for direct debit or not
                and rate['payment_method'] in [None, "DIRECT_DEBIT"]
            )

            consumption_kwh = float(consumption['consumptionDelta']) / 1000
            cost = float("{:.4f}".format(consumption_kwh * matching_rate['value_inc_vat']))

            period_costs.append({
                'period_end': read_time,
                'consumption_kwh': consumption_kwh,
                'rate': matching_rate['value_inc_vat'],
                'calculated_cost': cost,
            })

        return period_costs

    def _get_potential_tariff_rates(self, tariff: Tariff, region_code: str) -> Tuple[float, list[dict], str]:
        """
        Get rates for a specific tariff and region
        """

        all_products = self.query_service.execute_rest_query(f"{config.BASE_URL}/products/?brand=OCTOPUS_ENERGY&is_business=false")
        product = next((
            product for product in all_products['results']
            if product['display_name'] == tariff.api_display_name
            and product['direction'] == "IMPORT"
        ), None)

        if not product:
            raise ValueError(f"No matching tariff found for {tariff.api_display_name}")

        product_code = product.get('code')
        if product_code is None:
            raise ValueError(f"No product code found for {tariff.api_display_name}")

        product_link = next((
            item.get('href') for item in product.get('links', [])
            if item.get('rel', '').lower() == 'self'
        ), None)
        if not product_link:
            raise ValueError(f"Self link not found for tariff {product_code}.")

        tariff_details = self.query_service.execute_rest_query(product_link)

        # Get the standing charge including VAT
        region_code_key = f'_{region_code}'
        filtered_region = tariff_details.get('single_register_electricity_tariffs', {}).get(region_code_key)

        if filtered_region is None:
            raise ValueError(f"Region code not found: {region_code_key}")

        region_tariffs = filtered_region.get('direct_debit_monthly') or filtered_region.get('varying')
        standing_charge_inc_vat = region_tariffs.get('standing_charge_inc_vat')

        if standing_charge_inc_vat is None:
            raise ValueError(f"Standing charge including VAT not found for region {region_code_key}.")

        # Find the link for standard unit rates
        region_links = region_tariffs.get('links', [])
        unit_rates_link = next((
            item.get('href') for item in region_links
            if item.get('rel', '').lower() == 'standard_unit_rates'
        ), None)

        if not unit_rates_link:
            raise ValueError(f"Standard unit rates link not found for region: {region_code_key}")

        # Get today's rates
        today = date.today()
        unit_rates_link_with_time = f"{unit_rates_link}?period_from={today}T00:00:00Z&period_to={today}T23:59:59Z"
        unit_rates = self.query_service.execute_rest_query(unit_rates_link_with_time)

        return standing_charge_inc_vat, unit_rates.get('results', []), product_code
