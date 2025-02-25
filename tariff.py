class Tariff:
    def __init__(self,
                 id: str, display_name: str, api_display_name: str, tariff_code_matcher: str,
                 url_tariff_name: str, switchable: bool):
        self.id = id  # Represents the unique identifier for the tariff.
        self.display_name = display_name  # The user-friendly name of the tariff for display purposes.
        self.api_display_name = api_display_name  # The name used for API interactions with the tariff.
        self.tariff_code_matcher = tariff_code_matcher  # A string used to match against current tariff names to determine applicability.
        self.url_tariff_name = url_tariff_name  # The tariff name formatted for use in URLs.
        self.switchable = switchable  # Whether this tariff can be switched to or not

    def is_tariff(self, current_tariff_name: str) -> bool:
        """Check if the given tariff name matches the tariff code matcher."""
        return self.tariff_code_matcher.lower() in current_tariff_name.lower()

    def __eq__(self, other):
        """Compare two tariffs based on their ID."""
        if isinstance(other, Tariff):
            return self.id == other.id
        return False

    def __hash__(self):
        return hash(self.id)

    def __str__(self):
        return f"Tariff(id={self.id}, display_name={self.display_name}, api_display_name={self.api_display_name}, tariff_code_matcher={self.tariff_code_matcher}, url_tariff_name={self.url_tariff_name}, switchable={self.switchable})"


TARIFFS = [
    Tariff("go", "Octopus Go", "Octopus Go", "go", "go", True), # Octopus Go
    Tariff("agile", "Agile Octopus", "Agile Octopus", "agile", "agile", True), # Octopus Agile
    Tariff("cosy", "Cosy Octopus", "Cosy Octopus", "cosy", "cosy-octopus", True), # Octopus Cosy
    Tariff("flexible", "Flexible Octopus", "Flexible Octopus", "var", "", False) # Flexible Octopus
]
