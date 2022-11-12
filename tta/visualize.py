from typing import Set, Union

from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt


DEFAULT_WIDTH = 6.0
DEFAULT_HEIGHT = 1.5
SIZE_SMALL = 9  # Caption size in the pml book


def latexify(
    width_scale_factor=1,
    height_scale_factor=1,
    fig_width=None,
    fig_height=None,
    font_size=SIZE_SMALL,
):
    f"""
    width_scale_factor: float, DEFAULT_WIDTH will be divided by this number, DEFAULT_WIDTH is page width: {DEFAULT_WIDTH} inches.
    height_scale_factor: float, DEFAULT_HEIGHT will be divided by this number, DEFAULT_HEIGHT is {DEFAULT_HEIGHT} inches.
    fig_width: float, width of the figure in inches (if this is specified, width_scale_factor is ignored)
    fig_height: float, height of the figure in inches (if this is specified, height_scale_factor is ignored)
    font_size: float, font size
    """
    if fig_width is None:
        fig_width = DEFAULT_WIDTH / width_scale_factor
    if fig_height is None:
        fig_height = DEFAULT_HEIGHT / height_scale_factor

    # use TrueType fonts so they are embedded
    # https://stackoverflow.com/questions/9054884/how-to-embed-fonts-in-pdfs-produced-by-matplotlib
    # https://jdhao.github.io/2018/01/18/mpl-plotting-notes-201801/
    plt.rcParams["pdf.fonttype"] = 42

    # Font sizes
    # SIZE_MEDIUM = 14
    # SIZE_LARGE = 24
    # https://stackoverflow.com/a/39566040
    plt.rc("font", size=font_size)  # controls default text sizes
    plt.rc("axes", titlesize=font_size)  # fontsize of the axes title
    plt.rc("axes", labelsize=font_size)  # fontsize of the x and y labels
    plt.rc("xtick", labelsize=font_size)  # fontsize of the tick labels
    plt.rc("ytick", labelsize=font_size)  # fontsize of the tick labels
    plt.rc("legend", fontsize=font_size)  # legend fontsize
    plt.rc("figure", titlesize=font_size)  # fontsize of the figure title

    # latexify: https://nipunbatra.github.io/blog/posts/2014-06-02-latexify.html
    plt.rcParams["backend"] = "ps"
    plt.rc("text", usetex=True)
    plt.rc("font", family="serif")
    plt.rc("figure", figsize=(fig_width, fig_height))


ylabels = {
    "mean": "Average probability of class 1",
    "l1": "Average L1 error of class 1",
    "auc": "Average AUC",
    "auc_Z": "Average AUC (Z)",
    "accuracy": "Accuracy",
    "accuracy_Z": "Accuracy (Z)",
    "norm": "Euclidean distance",
}


def plot(
    npz_path: Path,
    train_batch_size: int,
    confounder_strength: np.ndarray,
    train_domains_set: Set[int],
    dataset_label_noise: float,
    plot_title: str,
    plot_root: Path,
    config_name: str,
):
    all_sweeps = np.load(npz_path, allow_pickle=True)

    for sweep_type, sweeps in all_sweeps.items():
        fig, ax = plt.subplots(figsize=(12, 6))

        if sweep_type == "accuracy":
            if dataset_label_noise > 0:
                upper_bound = bayes_accuracy(dataset_label_noise, confounder_strength)
                ax.plot(
                    confounder_strength,
                    upper_bound,
                    color="grey",
                    linestyle=":",
                    label="Upper bound",
                )

        sweeps = sweeps[0]
        oracle_sweep = sweeps.pop(("Oracle", None, train_batch_size))
        ax.plot(confounder_strength, oracle_sweep[:-1], linestyle="--", label="Oracle")
        unadapted_sweep = sweeps.pop(("Unadapted", None, train_batch_size))
        ax.plot(
            confounder_strength, unadapted_sweep[:-1], linestyle="--", label="Unadapted"
        )

        for (label, _, _), sweep in sweeps.items():
            ax.plot(confounder_strength, sweep[:-1], label=label)

        for i in train_domains_set:
            ax.axvline(confounder_strength[i], linestyle=":")

        plt.ylim((0, 1))
        plt.xlabel("Shift parameter")
        plt.ylabel(ylabels[sweep_type])
        plt.title(plot_title)
        plt.grid(True)
        plt.legend()

        for suffix in ("png", "pdf"):
            plt.savefig(plot_root / f"{config_name}_{sweep_type}.{suffix}", dpi=300)

        plt.close(fig)


def bayes_accuracy(
    dataset_label_noise: float, confounder_strength: Union[float, np.ndarray]
) -> np.ndarray:
    upper_bound = np.maximum(
        np.maximum(1 - confounder_strength, confounder_strength),
        (1 - dataset_label_noise) * np.ones_like(confounder_strength),
    )
    return upper_bound
