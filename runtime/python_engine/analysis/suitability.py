
import matplotlib.pyplot as plt
import numpy as np


def calculate_suitability(terrain):
    """
    Calculate a terrain suitability score between 0 and 1.

    This is a prototype index, not a validated rover
    mobility prediction.
    """

    slope = terrain["slope"]
    roughness = terrain["roughness"]
    hazard = terrain["hazard"]

    slope_score = np.clip(1 - slope / 30, 0, 1)
    roughness_score = np.clip(1 - roughness / 20, 0, 1)
    hazard_score = np.clip(1 - hazard, 0, 1)

    suitability = (
        0.4 * slope_score
        + 0.3 * roughness_score
        + 0.3 * hazard_score
    )

    suitability[~terrain["traversable"]] = 0

    return suitability


def plot_terrain(terrain, path=None, start=None, goal=None):
    """
    Display elevation, suitability and rover route.
    """

    elevation = terrain["elevation"]
    suitability = calculate_suitability(terrain)

    fig, axes = plt.subplots(1, 2, figsize=(15, 6))

    # Elevation map
    elevation_plot = axes[0].imshow(
        elevation,
        cmap="terrain",
        origin="upper"
    )

    axes[0].set_title("Simulated Martian Elevation")
    axes[0].set_xlabel("Grid Column")
    axes[0].set_ylabel("Grid Row")

    fig.colorbar(
        elevation_plot,
        ax=axes[0],
        label="Elevation (simulated metres)"
    )

    # Suitability map
    suitability_plot = axes[1].imshow(
        suitability,
        cmap="RdYlGn",
        vmin=0,
        vmax=1,
        origin="upper"
    )

    axes[1].set_title("Terrain Suitability")
    axes[1].set_xlabel("Grid Column")
    axes[1].set_ylabel("Grid Row")

    fig.colorbar(
        suitability_plot,
        ax=axes[1],
        label="Suitability score"
    )

    # Display rover route
    if path:
        rows = [point[0] for point in path]
        cols = [point[1] for point in path]

        for ax in axes:
            ax.plot(
                cols,
                rows,
                color="blue",
                linewidth=2,
                label="Rover route"
            )

    # Display start and destination
    if start:
        for ax in axes:
            ax.scatter(
                start[1], start[0],
                color="cyan",
                edgecolors="black",
                s=100,
                label="Start"
            )

    if goal:
        for ax in axes:
            ax.scatter(
                goal[1], goal[0],
                color="red",
                edgecolors="black",
                s=100,
                label="Destination"
            )

    for ax in axes:
        ax.legend(loc="upper right")

    plt.tight_layout()
    plt.show()
