import re

class Tariff:
    def __init__(self,
                 id: str, display_name: str, api_display_name: str, tariff_code_matcher: str,
                 url_tariff_name: str, switchable: bool, product_code: str = None,
                 can_leave: bool = True):
        self.id = id  # Represents the unique identifier for the tariff.
        self.display_name = display_name  # The user-friendly name of the tariff for display purposes.
        self.api_display_name = api_display_name  # The name used for API interactions with the tariff.
        self.tariff_code_matcher = tariff_code_matcher  # A string used to match against current tariff names to determine applicability.
        self.url_tariff_name = url_tariff_name  # The tariff name formatted for use in URLs.
        self.switchable = switchable  # Whether this tariff can be switched to or not
        self.product_code = product_code # Product code used in API e.g. "GO-VAR-22-10-14"
        # Whether the bot is allowed to switch away from this tariff (False for locked/unknown products).
        self.can_leave = can_leave

    @classmethod
    def unrecognised(cls, tariff_code: str, product_code: str = None, display_name: str = None) -> "Tariff":
        """Placeholder for a live tariff we can cost from telemetry but not switch to or from."""
        label = display_name or product_code or tariff_code
        return cls(
            id=f"current:{tariff_code}",
            display_name=label,
            api_display_name=label,
            tariff_code_matcher=re.escape(tariff_code),
            url_tariff_name="",
            switchable=False,
            product_code=product_code,
            can_leave=False,
        )

    def is_tariff(self, current_tariff_name: str) -> bool:
        """Check if the given tariff name matches the tariff code matcher using regex."""
        return re.search(self.tariff_code_matcher, current_tariff_name,  re.IGNORECASE) is not None

    def __eq__(self, other):
        """Compare two tariffs based on their ID."""
        if isinstance(other, Tariff):
            return self.id == other.id
        return False

    def __hash__(self):
        return hash(self.id)

    def __str__(self):
        return (
            f"Tariff(id={self.id}, display_name={self.display_name}, api_display_name={self.api_display_name}, "
            f"tariff_code_matcher={self.tariff_code_matcher}, url_tariff_name={self.url_tariff_name}, "
            f"switchable={self.switchable}, can_leave={self.can_leave}, product_code={self.product_code})"
        )


TARIFFS = [
    Tariff("go", "Octopus Go", "Octopus Go", r"-go-var-", "go", True), # Octopus Go (Variable)
    Tariff("go-fix-12m", "Octopus Go 12M Fixed", "Octopus Go 12M Fixed", r"-go-fix-", "go", True, can_leave=False),
    Tariff("agile", "Agile Octopus", "Agile Octopus", r"-agile-", "agile", True), # Octopus Agile
    Tariff("cosy", "Cosy Octopus", "Cosy Octopus", r"-cosy-(?!.*fix)", r"cosy-octopus", True), # Octopus Cosy (Variable is the default so don't match anything with 'fix' in the name)
    Tariff("flexible", "Flexible Octopus", "Flexible Octopus", r"(?<!go-)var", "", False) # Flexible Octopus
]


def match_known_tariff(tariff_code: str):
    return next((tariff for tariff in TARIFFS if tariff.is_tariff(tariff_code)), None)
