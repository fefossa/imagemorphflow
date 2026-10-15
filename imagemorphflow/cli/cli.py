import click
from imagemorphflow.cli.commands.doctor import doctor

from imagemorphflow import __version__
from imagemorphflow.cli.commands.run_pipeline import build_config, run_pipeline


@click.group()
@click.version_option(__version__, prog_name="imagemorphflow")
def cli():
    """ImageMorphFlow: image-based profiling pipelines."""


cli.add_command(run_pipeline)
cli.add_command(build_config)

cli.add_command(doctor)
