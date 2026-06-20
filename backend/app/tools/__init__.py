from app.tools.lodging_area_tool import MockLodgingAreaTool
from app.tools.official_site_tool import MockOfficialSiteTool
from app.tools.places_tool import MockPlacesTool
from app.tools.restaurant_tool import MockRestaurantTool
from app.tools.review_tool import MockReviewTool
from app.tools.transit_tool import MockTransitTool
from app.tools.weather_tool import MockWeatherTool


class ToolRegistry:
    def __init__(self) -> None:
        self.official = MockOfficialSiteTool()
        self.places = MockPlacesTool()
        self.reviews = MockReviewTool()
        self.weather = MockWeatherTool()
        self.transit = MockTransitTool()
        self.restaurant = MockRestaurantTool()
        self.lodging = MockLodgingAreaTool()
