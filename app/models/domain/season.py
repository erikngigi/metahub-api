"""Domain models for season lists and per-season episode lists."""

from datetime import date

from pydantic import BaseModel, Field

from app.models.domain.media import Series


class Season(BaseModel):
    """One season of a series, as a summary."""

    source: str = Field(description="Provider name.", examples=["tvmaze"])
    source_id: str = Field(
        description="Season ID to pass to the episodes route. This is the provider's global "
        "season ID, not the season number.",
        examples=["season:2696"],
    )
    season_number: int | None = Field(default=None, description="Season number within the show.", examples=[1])
    name: str | None = Field(default=None, description="Season title; `null` for most shows.")
    episode_count: int | None = Field(
        default=None, description="Episode count as announced by the provider. `null` if unknown.", examples=[7]
    )
    premiere_date: date | None = Field(default=None, description="Date the season started airing.")
    end_date: date | None = Field(default=None, description="Date the season finished airing.")
    network: str | None = Field(default=None, description="Broadcaster or streaming service.", examples=["NBC"])
    plot: str | None = Field(default=None, description="Season summary as plain text.")
    poster_url: str | None = Field(default=None, description="Season poster URL, or `null`.")


class SeasonsResponse(BaseModel):
    """A series together with its seasons."""

    series: Series = Field(description="Details of the show the seasons belong to.")
    seasons: list[Season] = Field(description="Seasons in ascending season-number order.")


class EpisodeListItem(BaseModel):
    """One episode in a season's episode list."""

    source: str = Field(description="Provider name.", examples=["tvmaze"])
    episode_id: str = Field(description="The provider's own ID for this episode.", examples=["59360"])
    season: int | None = Field(default=None, description="Season number.", examples=[1])
    number: int | None = Field(
        default=None, description="Episode number within the season. `null` for some specials.", examples=[1]
    )
    type: str | None = Field(
        default=None,
        description="`regular`, `significant_special` or `insignificant_special`.",
        examples=["regular"],
    )
    name: str = Field(description="Episode title.", examples=["Unknown Trouble"])
    air_date: date | None = Field(default=None, description="Original air date; `null` if unaired.")
    runtime_minutes: int | None = Field(default=None, description="Length in minutes.", examples=[60])
    rating: float | None = Field(default=None, description="User rating out of 10; `null` if unrated.")
    episode_format_listing: str | None = Field(default=None, description="Episode format listing")


class SeasonDetailsResponse(BaseModel):
    """One season together with its episodes."""

    season: Season = Field(description="Summary of the season.")
    episodes: list[EpisodeListItem] = Field(description="Episodes in season order.")


class SeasonEpisodesResponse(BaseModel):
    """Episodes of one season."""

    season_id: str = Field(description="The season ID that was requested.", examples=["season:2696"])
    count: int = Field(description="Number of episodes returned.", examples=[7])
    episodes: list[EpisodeListItem] = Field(description="Episodes in TVMaze's order, which is airing order.")
