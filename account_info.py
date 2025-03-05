from tariff import Tariff


class AccountInfo:
    def __init__(self, current_tariff: Tariff, standing_charge: float, region_code: str, consumption, mpan: str):
        self.current_tariff = current_tariff
        self.standing_charge = standing_charge
        self.region_code = region_code
        self.consumption = consumption
        self.mpan = mpan
