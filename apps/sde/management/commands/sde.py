import argparse
import hashlib
import json
import logging
import shutil
import subprocess
import zipfile
from pathlib import Path
from pathlib import Path as _Path
from typing import Any
from warnings import deprecated

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.sde.models import Checksum
from apps.sde.models.agents import Agent
from apps.sde.models.agents_in_space import AgentsInSpace
from apps.sde.models.ancestries import Ancestry
from apps.sde.models.asteroid_belts import AsteroidBelt
from apps.sde.models.bloodlines import Bloodline
from apps.sde.models.blueprints import Blueprint
from apps.sde.models.categories import Category
from apps.sde.models.certificates import Certificate
from apps.sde.models.character_attributes import CharacterAttribute
from apps.sde.models.constellations import Constellation
from apps.sde.models.contraband_types import ContrabandType
from apps.sde.models.control_tower_resources import ControlTowerResource
from apps.sde.models.corporation_activities import CorporationActivity
from apps.sde.models.dogma_attribute_categories import DogmaAttributeCategory
from apps.sde.models.dogma_attributes import DogmaAttribute
from apps.sde.models.dogma_effects import DogmaEffect
from apps.sde.models.factions import Faction
from apps.sde.models.graphic_ids import GraphicId
from apps.sde.models.groups import Group
from apps.sde.models.icon_ids import IconId
from apps.sde.models.inv_flags import InvFlag
from apps.sde.models.inv_items import InvItem
from apps.sde.models.inv_names import InvName
from apps.sde.models.inv_positions import InvPosition
from apps.sde.models.inv_unique_names import InvUniqueName
from apps.sde.models.market_groups import MarketGroup
from apps.sde.models.meta_groups import MetaGroup
from apps.sde.models.moons import Moon
from apps.sde.models.npc_corporation_divisions import NpcCorporationDivision
from apps.sde.models.npc_corporations import NpcCorporation
from apps.sde.models.planet_resources import PlanetResource
from apps.sde.models.planet_schematics import PlanetSchematic
from apps.sde.models.planets import Planet
from apps.sde.models.races import Race
from apps.sde.models.regions import Region
from apps.sde.models.research_agents import ResearchAgent
from apps.sde.models.skin_licenses import SkinLicense
from apps.sde.models.skin_materials import SkinMaterial
from apps.sde.models.skins import Skin
from apps.sde.models.solar_systems import SolarSystem
from apps.sde.models.sovereignty_upgrades import SovereigntyUpgrade
from apps.sde.models.sta_stations import StaStation
from apps.sde.models.stars import Star
from apps.sde.models.station_operations import StationOperation
from apps.sde.models.station_services import StationService
from apps.sde.models.tournament_rule_sets import TournamentRuleSet
from apps.sde.models.type_dogma import TypeDogma
from apps.sde.models.type_materials import TypeMaterial
from apps.sde.models.types import Type
from apps.sde.models.universe_lookup import UniverseLookup

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Perform SDE tasks'

    workspace_dir = Path(settings.SDE_WORKSPACE)
    local_checksums = {}
    remote_checksums = {}

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            '--force-download',
            action='store_true',
            help='Force fresh download and import of the SDE',
        )

        parser.add_argument(
            '--skip-yaml-to-json',
            action='store_true',
            help='Skip the YAML to JSON conversion step',
        )

        parser.add_argument(
            '--download-only',
            action='store_true',
            help='Only download the SDE and extract, skip further processing',
        )

    # Setup the SDE workspace
    def setup_workspace(self) -> None:
        logger.info('Setting up workspace for SDE tasks')
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

    # Query ESI remote endpoint for file checksums
    def get_remote_checksums(self):
        if not self.remote_checksums:
            res = httpx.get(settings.SDE_CHECKSUM_URL)
            if res.status_code == 200:  # noqa: PLR2004
                for line in res.text.splitlines():
                    checksum, name = line.strip().split()
                    self.remote_checksums[name] = checksum

    # Query the local database for file checksums that are active in the database
    def get_local_checksums(self):
        checksums = Checksum.objects.all()
        self.local_checksums = {cs.name: cs.checksum for cs in checksums}

    # Lookup a checksum of applied files
    def local_checksum_lookup(self, name: str) -> str:
        return dict(self.local_checksums).get(name, '')

    # lookup the latest checksum of remote files
    def remote_checksum_lookup(self, name: str) -> str:
        return self.remote_checksums.get(name, '')

    def validate_checksum(self, name: str) -> bool:
        local_checksum = self.local_checksum_lookup(name)
        remote_checksum = self.remote_checksum_lookup(name)
        if local_checksum != remote_checksum:
            logger.warning(
                f'Checksum mismatch for {name} - local: {local_checksum}, remote: {remote_checksum}'
            )
            return False
        logger.info(f'Checksum match for {name} - {local_checksum}')
        return True

    # validate SDE zip checksum
    def validate_sde_zip_checksum(self) -> bool:
        logger.info('Validating SDE zip checksum')
        md5_hash = hashlib.md5(usedforsecurity=False)
        try:
            with zipfile.ZipFile(
                self.workspace_dir / 'sde.zip', 'r', zipfile.ZIP_DEFLATED
            ) as z:
                file_name = z.namelist()
                for f in file_name:
                    md5_hash.update(z.read(f))
        except zipfile.BadZipFile:
            logger.exception('Bad zip file')
            return False

        checksum = md5_hash.hexdigest()
        remote_checksum = self.remote_checksum_lookup('sde.zip')
        if checksum != remote_checksum:
            logger.error(
                f'SDE checksum failed - got {checksum}, expected {remote_checksum}'
            )
            return False
        logger.info(f'SDE checksum passed for {checksum}')
        Checksum.objects.update_or_create(
            name='sde.zip',
            checksum=checksum,
        )
        return True

    # Download the SDE data
    def download_sde(self, force_download: bool) -> None:
        needs_download = False
        if Path(self.workspace_dir / 'sde.zip').exists() and not force_download:
            logger.info('SDE zip already exists, validating checksums...')
            if not self.validate_sde_zip_checksum():
                logger.info('SDE zip checksum is invalid, re-downloading...')
                needs_download = True
            else:
                logger.info('SDE zip checksum is valid, skipping download')
                needs_download = False
        else:
            needs_download = True

        # Implement the download logic here
        if force_download or needs_download:
            if force_download:
                logger.info('Forcing fresh download of SDE')
            logger.info('Downloading SDE data...')
            Path(self.workspace_dir / 'sde.zip').unlink(missing_ok=True)
            # Implement the download logic here
            chunk_size = 1 * 1024**2
            with (
                httpx.stream('GET', settings.SDE_ARCHIVE_URL) as r,
                Path(self.workspace_dir / 'sde.zip').open('wb') as f,
            ):
                for chunk in r.iter_bytes(chunk_size=chunk_size):
                    f.write(chunk)
            self.validate_sde_zip_checksum()
            logger.info(
                f'SDE archive downloaded to {Path(self.workspace_dir / "sde.zip").absolute().resolve()}'
            )

    def extract_sde(self) -> None:
        if Path(self.workspace_dir / '.sde_extracted').is_file():
            logger.info('SDE zip file already extracted, skipping extraction')
            return
        try:
            with zipfile.ZipFile(self.workspace_dir / 'sde.zip', 'r') as z:
                z.extractall(self.workspace_dir)
            Path(self.workspace_dir / '.sde_extracted').touch()
        except Exception:
            logger.exception('Failed to extract SDE zip file')
            return

    def run_yaml_to_json_conversion(self) -> None:
        """Run the repository script that converts SDE YAML files to JSON.

        The script lives at scripts/convert-sde-yaml-to-json.sh in the repo root.
        Prefer settings.BASE_DIR when available, otherwise fall back to cwd.
        """
        if Path(self.workspace_dir / '.convert_to_json_done').is_file():
            logger.info('YAML->JSON conversion already done, skipping')
            return
        repo_root = Path(getattr(settings, 'BASE_DIR', _Path.cwd()))
        script_path = repo_root / 'scripts' / 'convert-sde-yaml-to-json.sh'
        if not script_path.exists():
            logger.warning(
                'Conversion script not found at %s, skipping YAML->JSON conversion',
                script_path,
            )
            return

        cmd = [str(script_path), str(self.workspace_dir)]
        logger.info('Running YAML->JSON conversion script: %s', ' '.join(cmd))
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
        except Exception:
            logger.exception('Failed to run conversion script')
            return

        # delete unneeded files
        shutil.rmtree(str(Path(self.workspace_dir / 'universe' / 'hidden').resolve()))

        if res.stdout:
            logger.debug('Conversion stdout: %s', res.stdout)
        if res.stderr:
            logger.warning('Conversion stderr: %s', res.stderr)

        if res.returncode != 0:
            logger.error('Conversion script failed with exit code %s', res.returncode)
        else:
            Path(self.workspace_dir / '.convert_to_json_done').touch()
            logger.info('YAML->JSON conversion completed successfully')

    def get_file_checksum(self, file_path: Path) -> str:
        """Calculate the MD5 checksum of a file."""
        # Ensure we have a Path object and the file exists
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            logger.warning('File for checksum not found or not a file: %s', path)
            return ''

        md5_hash = hashlib.md5()  # noqa: S324
        try:
            # Read and update hash string value in blocks (8K buffer)
            with path.open('rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    md5_hash.update(chunk)
        except Exception:
            logger.exception('Failed calculating checksum for %s', path)
            return ''

        return md5_hash.hexdigest()

    def build_file_path(self, sub_path: str, filename: str) -> tuple[Path, Path]:
        filename_base = filename.rsplit('.', 1)[0]  # Remove extension if present
        return (
            Path(settings.SDE_WORKSPACE / sub_path / f'{filename_base}.json'),
            Path(settings.SDE_WORKSPACE / sub_path / f'{filename_base}.yaml'),
        )

    def load_bsd_inv_flags(self) -> None:
        logger.info('Loading invFlags from BSD data...')
        json_file, yaml_file = self.build_file_path('bsd', 'invFlags')
        existing_checksum = self.local_checksum_lookup('bsd/invFlags.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('invFlags.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for item in data:
                    records.extend(
                        [
                            InvFlag(
                                flag_id=item.get('flagID'),
                                flag_name=item.get('flagName'),
                                flag_text=item.get('flagText'),
                                order_id=item.get('orderID'),
                            )
                        ]
                    )
            InvFlag.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=['flag_name', 'flag_text', 'order_id'],
                unique_fields=['flag_id'],
            )
        except Exception:
            logger.exception('Failed loading invFlags from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='bsd/invFlags.yaml',
            checksum=checksum,
        )

    def load_bsd_inv_items(self) -> None:
        logger.info('Loading invItems from BSD data...')
        json_file, yaml_file = self.build_file_path('bsd', 'invItems')
        existing_checksum = self.local_checksum_lookup('bsd/invItems.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('invItems.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for item in data:
                    records.extend(
                        [
                            InvItem(
                                item_id=item.get('itemID'),
                                flag_id=item.get('flagID'),
                                location_id=item.get('locationID'),
                                owner_id=item.get('ownerID'),
                                quantity=item.get('quantity'),
                                type_id=item.get('typeID'),
                            )
                        ]
                    )
            InvItem.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=[
                    'flag_id',
                    'location_id',
                    'owner_id',
                    'quantity',
                    'type_id',
                ],
                unique_fields=['item_id'],
            )
        except Exception:
            logger.exception('Failed loading invItems from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='bsd/invItems.yaml',
            checksum=checksum,
        )

    def load_bsd_inv_names(self) -> None:
        logger.info('Loading invNames from BSD data...')
        json_file, yaml_file = self.build_file_path('bsd', 'invNames')
        existing_checksum = self.local_checksum_lookup('bsd/invNames.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('invNames.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for item in data:
                    records.extend(
                        [
                            InvName(
                                item_id=item.get('itemID'),
                                item_name=item.get('itemName'),
                            )
                        ]
                    )
            InvName.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=['item_name'],
                unique_fields=['item_id'],
            )
        except Exception:
            logger.exception('Failed loading invNames from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='bsd/invNames.yaml',
            checksum=checksum,
        )

    def load_bsd_inv_positions(self) -> None:
        logger.info('Loading invPositions from BSD data...')
        json_file, yaml_file = self.build_file_path('bsd', 'invPositions')
        existing_checksum = self.local_checksum_lookup('bsd/invPositions.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('invPositions.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for item in data:
                    records.extend(
                        [
                            InvPosition(
                                item_id=item.get('itemID'),
                                pitch=item.get('pitch'),
                                roll=item.get('roll'),
                                yaw=item.get('yaw'),
                                x=item.get('x'),
                                y=item.get('y'),
                                z=item.get('z'),
                            )
                        ]
                    )
            InvPosition.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=['pitch', 'roll', 'yaw', 'x', 'y', 'z'],
                unique_fields=['item_id'],
            )
        except Exception:
            logger.exception('Failed loading invPositions from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='bsd/invPositions.yaml',
            checksum=checksum,
        )

    def load_bsd_inv_unique_names(self) -> None:
        logger.info('Loading invUniqueNames from BSD data...')
        json_file, yaml_file = self.build_file_path('bsd', 'invUniqueNames')
        existing_checksum = self.local_checksum_lookup('bsd/invUniqueNames.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('invUniqueNames.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for item in data:
                    records.extend(
                        [
                            InvUniqueName(
                                item_id=item.get('itemID'),
                                group_id=item.get('groupID'),
                                item_name=item.get('itemName'),
                            )
                        ]
                    )
            InvUniqueName.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=['group_id', 'item_name'],
                unique_fields=['item_id'],
            )
        except Exception:
            logger.exception('Failed loading invUniqueNames from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='bsd/invUniqueNames.yaml',
            checksum=checksum,
        )

    def load_bsd_sta_stations(self) -> None:
        logger.info('Loading staStations from BSD data...')
        json_file, yaml_file = self.build_file_path('bsd', 'staStations')
        existing_checksum = self.local_checksum_lookup('bsd/staStations.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('staStations.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for item in data:
                    records.extend(
                        [
                            StaStation(
                                station_id=item.get('stationID'),
                                security=item.get('security'),
                                station_type_id=item.get('stationTypeID'),
                                corporation_id=item.get('corporationID'),
                                solar_system_id=item.get('solarSystemID'),
                                constellation_id=item.get('constellationID'),
                                region_id=item.get('regionID'),
                                station_name=item.get('stationName'),
                                x=item.get('x'),
                                y=item.get('y'),
                                z=item.get('z'),
                                reprocessing_efficiency=item.get(
                                    'reprocessingEfficiency'
                                ),
                                reprocessing_stations_take=item.get(
                                    'reprocessingStationsTake'
                                ),
                                reprocessing_hangar_flag=item.get(
                                    'reprocessingHangarFlag'
                                ),
                                docking_cost_per_volume=item.get(
                                    'dockingCostPerVolume'
                                ),
                                max_ship_volume_dockable=item.get(
                                    'maxShipVolumeDockable'
                                ),
                                office_rental_cost=item.get('officeRentalCost'),
                                operation_id=item.get('operationID'),
                            )
                        ]
                    )
            StaStation.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=[
                    'security',
                    'station_type_id',
                    'corporation_id',
                    'solar_system_id',
                    'constellation_id',
                    'region_id',
                    'station_name',
                    'x',
                    'y',
                    'z',
                    'reprocessing_efficiency',
                    'reprocessing_stations_take',
                    'reprocessing_hangar_flag',
                    'docking_cost_per_volume',
                    'max_ship_volume_dockable',
                    'office_rental_cost',
                    'operation_id',
                ],
                unique_fields=['station_id'],
            )
        except Exception:
            logger.exception('Failed loading staStations from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='bsd/staStations.yaml',
            checksum=checksum,
        )

    def load_fsd_agents(self) -> None:
        logger.info('Loading agents from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'agents')
        existing_checksum = self.local_checksum_lookup('fsd/agents.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('agents.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            Agent(
                                id=k,
                                agent_type_id=v.get('agentTypeID'),
                                corporation_id=v.get('corporationID'),
                                division_id=v.get('divisionID'),
                                is_locator=v.get('isLocator'),
                                level=v.get('level'),
                                location_id=v.get('locationID'),
                            )
                        ]
                    )
            Agent.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=[
                    'agent_type_id',
                    'corporation_id',
                    'division_id',
                    'is_locator',
                    'level',
                    'location_id',
                ],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading agents from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/agents.yaml',
            checksum=checksum,
        )

    def load_fsd_agents_in_space(self) -> None:
        logger.info('Loading agentsInSpace from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'agentsInSpace')
        existing_checksum = self.local_checksum_lookup('fsd/agentsInSpace.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('agentsInSpace.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            AgentsInSpace(
                                id=k,
                                dungeon_id=v.get('dungeonID'),
                                solar_system_id=v.get('solarSystemID'),
                                spawn_point_id=v.get('spawnPointID'),
                                type_id=v.get('typeID'),
                            )
                        ]
                    )
            AgentsInSpace.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=[
                    'dungeon_id',
                    'solar_system_id',
                    'spawn_point_id',
                    'type_id',
                ],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading agentsInSpace from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/agentsInSpace.yaml',
            checksum=checksum,
        )

    def load_fsd_ancestries(self) -> None:
        logger.info('Loading ancestries from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'ancestries')
        existing_checksum = self.local_checksum_lookup('fsd/ancestries.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('ancestries.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            Ancestry(
                                id=k,
                                bloodline_id=v.get('bloodlineID'),
                                charisma=v.get('charisma'),
                                description_id=v.get('descriptionID'),
                                icon_id=v.get('iconID'),
                                intelligence=v.get('intelligence'),
                                memory=v.get('memory'),
                                name_id=v.get('nameID'),
                                perception=v.get('perception'),
                                short_description=v.get('shortDescription'),
                                willpower=v.get('willpower'),
                            )
                        ]
                    )
            Ancestry.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=[
                    'bloodline_id',
                    'charisma',
                    'description_id',
                    'icon_id',
                    'intelligence',
                    'memory',
                    'name_id',
                    'perception',
                    'short_description',
                    'willpower',
                ],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading ancestries from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/ancestries.yaml',
            checksum=checksum,
        )

    def load_fsd_bloodlines(self) -> None:
        logger.info('Loading bloodlines from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'bloodlines')
        existing_checksum = self.local_checksum_lookup('fsd/bloodlines.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('bloodlines.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            Bloodline(
                                id=k,
                                charisma=v.get('charisma'),
                                corporation_id=v.get('corporationID'),
                                description_id=v.get('descriptionID'),
                                icon_id=v.get('iconID'),
                                intelligence=v.get('intelligence'),
                                memory=v.get('memory'),
                                name_id=v.get('nameID'),
                                perception=v.get('perception'),
                                race_id=v.get('raceID'),
                                willpower=v.get('willpower'),
                            )
                        ]
                    )
            Bloodline.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=[
                    'charisma',
                    'corporation_id',
                    'description_id',
                    'icon_id',
                    'intelligence',
                    'memory',
                    'name_id',
                    'perception',
                    'race_id',
                    'willpower',
                ],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading bloodlines from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/bloodlines.yaml',
            checksum=checksum,
        )

    def load_fsd_blueprints(self) -> None:
        logger.info('Loading blueprints from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'blueprints')
        existing_checksum = self.local_checksum_lookup('fsd/blueprints.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('blueprints.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            Blueprint(
                                id=k,
                                activities=v.get('activities'),
                                blueprint_type_id=v.get('blueprintTypeID'),
                                max_production_limit=v.get('maxProductionLimit'),
                            )
                        ]
                    )
            Blueprint.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=[
                    'activities',
                    'blueprint_type_id',
                    'max_production_limit',
                ],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading blueprints from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/blueprints.yaml',
            checksum=checksum,
        )

    def load_fsd_categories(self) -> None:
        logger.info('Loading categories from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'categories')
        existing_checksum = self.local_checksum_lookup('fsd/categories.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('categories.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            Category(
                                id=k,
                                name=v.get('name'),
                                published=v.get('published'),
                                icon_id=v.get('iconID'),
                            )
                        ]
                    )
            Category.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=['name', 'published', 'icon_id'],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading categories from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/categories.yaml',
            checksum=checksum,
        )

    def load_fsd_certificates(self) -> None:
        logger.info('Loading certificates from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'certificates')
        existing_checksum = self.local_checksum_lookup('fsd/certificates.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('certificates.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            Certificate(
                                id=k,
                                description=v.get('description'),
                                group_id=v.get('groupID'),
                                name=v.get('name'),
                                recommended_for=v.get('recommendedFor'),
                                skill_types=v.get('skillTypes'),
                            )
                        ]
                    )
            Certificate.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=[
                    'description',
                    'group_id',
                    'name',
                    'recommended_for',
                    'skill_types',
                ],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading certificates from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/certificates.yaml',
            checksum=checksum,
        )

    def load_fsd_character_attributes(self) -> None:
        logger.info('Loading characterAttributes from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'characterAttributes')
        existing_checksum = self.local_checksum_lookup('fsd/characterAttributes.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info(
                'characterAttributes.yaml checksum matches existing, skipping load'
            )
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            CharacterAttribute(
                                id=k,
                                description=v.get('description'),
                                icon_id=v.get('iconID'),
                                name_id=v.get('nameID'),
                                notes=v.get('notes'),
                                short_description=v.get('shortDescription'),
                            )
                        ]
                    )
            CharacterAttribute.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=[
                    'description',
                    'icon_id',
                    'name_id',
                    'notes',
                    'short_description',
                ],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading characterAttributes from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/characterAttributes.yaml',
            checksum=checksum,
        )

    def load_fsd_contraband_types(self) -> None:
        logger.info('Loading contrabandTypes from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'contrabandTypes')
        existing_checksum = self.local_checksum_lookup('fsd/contrabandTypes.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('contrabandTypes.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            ContrabandType(
                                id=k,
                                factions=v.get('factions'),
                            )
                        ]
                    )
            ContrabandType.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=['factions'],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading contrabandTypes from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/contrabandTypes.yaml',
            checksum=checksum,
        )

    def load_fsd_control_tower_resources(self) -> None:
        logger.info('Loading controlTowerResources from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'controlTowerResources')
        existing_checksum = self.local_checksum_lookup('fsd/controlTowerResources.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info(
                'controlTowerResources.yaml checksum matches existing, skipping load'
            )
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            ControlTowerResource(
                                id=k,
                                resources=v.get('resources'),
                            )
                        ]
                    )
            ControlTowerResource.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=['resources'],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading controlTowerResources from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/controlTowerResources.yaml',
            checksum=checksum,
        )

    def load_fsd_corporation_activities(self) -> None:
        logger.info('Loading corporationActivities from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'corporationActivities')
        existing_checksum = self.local_checksum_lookup('fsd/corporationActivities.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info(
                'corporationActivities.yaml checksum matches existing, skipping load'
            )
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            CorporationActivity(
                                id=k,
                                name_id=v.get('nameID'),
                            )
                        ]
                    )
            CorporationActivity.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=['name_id'],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading corporationActivities from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/corporationActivities.yaml',
            checksum=checksum,
        )

    def load_fsd_dogma_attribute_categories(self) -> None:
        logger.info('Loading dogmaAttributeCategories from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'dogmaAttributeCategories')
        existing_checksum = self.local_checksum_lookup(
            'fsd/dogmaAttributeCategories.yaml'
        )
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info(
                'dogmaAttributeCategories.yaml checksum matches existing, skipping load'
            )
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            DogmaAttributeCategory(
                                id=k,
                                description=v.get('description'),
                                name=v.get('name'),
                            )
                        ]
                    )
            DogmaAttributeCategory.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=['description', 'name'],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception(
                'Failed loading dogmaAttributeCategories from %s', json_file
            )
            return
        Checksum.objects.update_or_create(
            name='fsd/dogmaAttributeCategories.yaml',
            checksum=checksum,
        )

    def load_fsd_dogma_attributes(self) -> None:
        logger.info('Loading dogmaAttributes from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'dogmaAttributes')
        existing_checksum = self.local_checksum_lookup('fsd/dogmaAttributes.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('dogmaAttributes.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            DogmaAttribute(
                                id=k,
                                attribute_id=v.get('attributeID'),
                                category_id=v.get('categoryID'),
                                data_type=v.get('dataType'),
                                default_value=v.get('defaultValue'),
                                description=v.get('description'),
                                high_is_good=v.get('highIsGood'),
                                name=v.get('name'),
                                published=v.get('published'),
                                stackable=v.get('stackable'),
                                display_name_id=v.get('displayNameID'),
                                icon_id=v.get('iconID'),
                                tooltip_description_id=v.get('tooltipDescriptionID'),
                                tooltip_title_id=v.get('tooltipTitleID'),
                                unit_id=v.get('unitID'),
                                charge_recharge_time_id=v.get('chargeRechargeTimeID'),
                                max_attribute_id=v.get('maxAttributeID'),
                                min_attribute_id=v.get('minAttributeID'),
                                display_when_zero=v.get('displayWhenZero'),
                            )
                        ]
                    )
            DogmaAttribute.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=[
                    'attribute_id',
                    'category_id',
                    'data_type',
                    'default_value',
                    'description',
                    'high_is_good',
                    'name',
                    'published',
                    'stackable',
                    'display_name_id',
                    'icon_id',
                    'tooltip_description_id',
                    'tooltip_title_id',
                    'unit_id',
                    'charge_recharge_time_id',
                    'max_attribute_id',
                    'min_attribute_id',
                    'display_when_zero',
                ],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading dogmaAttributes from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/dogmaAttributes.yaml',
            checksum=checksum,
        )

    def load_fsd_dogma_effects(self) -> None:
        logger.info('Loading dogmaEffects from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'dogmaEffects')
        existing_checksum = self.local_checksum_lookup('fsd/dogmaEffects.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('dogmaEffects.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            DogmaEffect(
                                id=k,
                                disallow_auto_repeat=v.get('disallowAutoRepeat'),
                                discharge_attribute_id=v.get('dischargeAttributeID'),
                                duration_attribute_id=v.get('durationAttributeID'),
                                effect_category=v.get('effectCategory'),
                                effect_id=v.get('effectID'),
                                effect_name=v.get('effectName'),
                                electronic_chance=v.get('electronicChance'),
                                guid=v.get('guid'),
                                is_assistance=v.get('isAssistance'),
                                is_offensive=v.get('isOffensive'),
                                is_warp_safe=v.get('isWarpSafe'),
                                propulsion_chance=v.get('propulsionChance'),
                                published=v.get('published'),
                                range_chance=v.get('rangeChance'),
                                distribution=v.get('distribution'),
                                falloff_attribute_id=v.get('falloffAttributeID'),
                                range_attribute_id=v.get('rangeAttributeID'),
                                tracking_speed_attribute_id=v.get(
                                    'trackingSpeedAttributeID'
                                ),
                                description_id=v.get('descriptionID'),
                                display_name_id=v.get('displayNameID'),
                                icon_id=v.get('iconID'),
                                modifier_info=v.get('modifierInfo'),
                                sfx_name=v.get('sfxName'),
                                npc_usage_chance_attribute_id=v.get(
                                    'npcUsageChanceAttributeID'
                                ),
                                npc_activation_chance_attribute_id=v.get(
                                    'npcActivationChanceAttributeID'
                                ),
                                fitting_usage_chance_attribute_id=v.get(
                                    'fittingUsageChanceAttributeID'
                                ),
                                resistance_attribute_id=v.get('resistanceAttributeID'),
                            )
                        ]
                    )
            DogmaEffect.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=[
                    'disallow_auto_repeat',
                    'discharge_attribute_id',
                    'duration_attribute_id',
                    'effect_category',
                    'effect_id',
                    'effect_name',
                    'electronic_chance',
                    'guid',
                    'is_assistance',
                    'is_offensive',
                    'is_warp_safe',
                    'propulsion_chance',
                    'published',
                    'range_chance',
                    'distribution',
                    'falloff_attribute_id',
                    'range_attribute_id',
                    'tracking_speed_attribute_id',
                    'description_id',
                    'display_name_id',
                    'icon_id',
                    'modifier_info',
                    'sfx_name',
                    'npc_usage_chance_attribute_id',
                    'npc_activation_chance_attribute_id',
                    'fitting_usage_chance_attribute_id',
                    'resistance_attribute_id',
                ],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading dogmaEffects from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/dogmaEffects.yaml',
            checksum=checksum,
        )

    def load_fsd_factions(self) -> None:
        logger.info('Loading factions from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'factions')
        existing_checksum = self.local_checksum_lookup('fsd/factions.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('factions.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            Faction(
                                id=k,
                                corporation_id=v.get('corporationID'),
                                description_id=v.get('descriptionID'),
                                flat_logo=v.get('flatLogo'),
                                flat_logo_with_name=v.get('flatLogoWithName'),
                                icon_id=v.get('iconID'),
                                member_races=v.get('memberRaces'),
                                militia_corporation_id=v.get('militiaCorporationID'),
                                name_id=v.get('nameID'),
                                short_description_id=v.get('shortDescriptionID'),
                                size_factor=v.get('sizeFactor'),
                                solar_system_id=v.get('solarSystemID'),
                                unique_name=v.get('uniqueName'),
                            )
                        ]
                    )
            Faction.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=[
                    'corporation_id',
                    'description_id',
                    'flat_logo',
                    'flat_logo_with_name',
                    'icon_id',
                    'member_races',
                    'militia_corporation_id',
                    'name_id',
                    'short_description_id',
                    'size_factor',
                    'solar_system_id',
                    'unique_name',
                ],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading factions from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/factions.yaml',
            checksum=checksum,
        )

    def load_fsd_graphic_ids(self) -> None:
        logger.info('Loading graphicIds from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'graphicIDs')
        existing_checksum = self.local_checksum_lookup('fsd/graphicIDs.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('graphicIDs.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            GraphicId(
                                id=k,
                                description=v.get('description'),
                                graphic_file=v.get('graphicFile'),
                                icon_info=v.get('iconInfo'),
                                sof_faction_name=v.get('sofFactionName'),
                                sof_hull_name=v.get('sofHullName'),
                                sof_race_name=v.get('sofRaceName'),
                                sof_layout=v.get('sofLayout'),
                            )
                        ]
                    )
            GraphicId.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=[
                    'description',
                    'graphic_file',
                    'icon_info',
                    'sof_faction_name',
                    'sof_hull_name',
                    'sof_race_name',
                    'sof_layout',
                ],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading graphicIDs from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/graphicIDs.yaml',
            checksum=checksum,
        )

    def load_fsd_groups(self) -> None:
        logger.info('Loading groups from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'groups')
        existing_checksum = self.local_checksum_lookup('fsd/groups.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('groups.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            Group(
                                id=k,
                                anchorable=v.get('anchorable'),
                                anchored=v.get('anchored'),
                                category_id=v.get('categoryID'),
                                fittable_non_singleton=v.get('fittableNonSingleton'),
                                name=v.get('name'),
                                published=v.get('published'),
                                use_base_price=v.get('useBasePrice'),
                                icon_id=v.get('iconID'),
                            )
                        ]
                    )
            Group.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=[
                    'anchorable',
                    'anchored',
                    'category_id',
                    'fittable_non_singleton',
                    'name',
                    'published',
                    'use_base_price',
                    'icon_id',
                ],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading groups from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/groups.yaml',
            checksum=checksum,
        )

    def load_fsd_icon_ids(self) -> None:
        logger.info('Loading iconIds from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'iconIDs')
        existing_checksum = self.local_checksum_lookup('fsd/iconIDs.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('iconIDs.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            IconId(
                                id=k,
                                description=v.get('description'),
                                icon_file=v.get('iconFile'),
                                obsolete=v.get('obsolete'),
                            )
                        ]
                    )
            IconId.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=['description', 'icon_file', 'obsolete'],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading iconIDs from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/iconIDs.yaml',
            checksum=checksum,
        )

    def load_fsd_market_groups(self) -> None:
        logger.info('Loading marketGroups from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'marketGroups')
        existing_checksum = self.local_checksum_lookup('fsd/marketGroups.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('marketGroups.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            MarketGroup(
                                id=k,
                                description_id=v.get('descriptionID'),
                                has_types=v.get('hasTypes'),
                                icon_id=v.get('iconID'),
                                name_id=v.get('nameID'),
                                parent_group_id=v.get('parentGroupID'),
                            )
                        ]
                    )
            MarketGroup.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=[
                    'description_id',
                    'has_types',
                    'icon_id',
                    'name_id',
                    'parent_group_id',
                ],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading marketGroups from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/marketGroups.yaml',
            checksum=checksum,
        )

    def load_fsd_meta_groups(self) -> None:
        logger.info('Loading metaGroups from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'metaGroups')
        existing_checksum = self.local_checksum_lookup('fsd/metaGroups.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('metaGroups.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            MetaGroup(
                                id=k,
                                color=v.get('color'),
                                name_id=v.get('nameID'),
                                icon_id=v.get('iconID'),
                                icon_suffix=v.get('iconSuffix'),
                                description_id=v.get('descriptionID'),
                            )
                        ]
                    )
            MetaGroup.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=[
                    'color',
                    'name_id',
                    'icon_id',
                    'icon_suffix',
                    'description_id',
                ],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading metaGroups from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/metaGroups.yaml',
            checksum=checksum,
        )

    def load_fsd_npc_corporation_divisions(self) -> None:
        logger.info('Loading npcCorporationDivisions from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'npcCorporationDivisions')
        existing_checksum = self.local_checksum_lookup(
            'fsd/npcCorporationDivisions.yaml'
        )
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info(
                'npcCorporationDivisions.yaml checksum matches existing, skipping load'
            )
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            NpcCorporationDivision(
                                id=k,
                                description=v.get('description'),
                                internal_name=v.get('internalName'),
                                leader_type_name_id=v.get('leaderTypeNameID'),
                                name_id=v.get('nameID'),
                                description_id=v.get('descriptionID'),
                            )
                        ]
                    )
            NpcCorporationDivision.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=[
                    'description',
                    'internal_name',
                    'leader_type_name_id',
                    'name_id',
                    'description_id',
                ],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception(
                'Failed loading npcCorporationDivisions from %s', json_file
            )
            return
        Checksum.objects.update_or_create(
            name='fsd/npcCorporationDivisions.yaml',
            checksum=checksum,
        )

    def load_fsd_npc_corporations(self) -> None:
        logger.info('Loading npcCorporations from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'npcCorporations')
        existing_checksum = self.local_checksum_lookup('fsd/npcCorporations.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('npcCorporations.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            NpcCorporation(
                                id=k,
                                ceo_id=v.get('ceoID'),
                                deleted=v.get('deleted'),
                                description_id=v.get('descriptionID'),
                                extent=v.get('extent'),
                                has_player_personnel_manager=v.get(
                                    'hasPlayerPersonnelManager'
                                ),
                                initial_price=v.get('initialPrice'),
                                member_limit=v.get('memberLimit'),
                                min_security=v.get('minSecurity'),
                                minimum_join_standing=v.get('minimumJoinStanding'),
                                name_id=v.get('nameID'),
                                public_shares=v.get('publicShares'),
                                send_char_termination_message=v.get(
                                    'sendCharTerminationMessage'
                                ),
                                shares=v.get('shares'),
                                size=v.get('size'),
                                station_id=v.get('stationID'),
                                tax_rate=v.get('taxRate'),
                                ticker_name=v.get('tickerName'),
                                unique_name=v.get('uniqueName'),
                                allowed_member_races=v.get('allowedMemberRaces'),
                                corporation_trades=v.get('corporationTrades'),
                                divisions=v.get('divisions'),
                                enemy_id=v.get('enemyID'),
                                faction_id=v.get('factionID'),
                                friend_id=v.get('friendID'),
                                icon_id=v.get('iconID'),
                                investors=v.get('investors'),
                                lp_offer_tables=v.get('lpOfferTables'),
                                main_activity_id=v.get('mainActivityID'),
                                race_id=v.get('raceID'),
                                size_factor=v.get('sizeFactor'),
                                solar_system_id=v.get('solarSystemID'),
                                exchange_rates=v.get('exchangeRates', {}),
                                secondary_activity_id=v.get('secondaryActivityID'),
                                url=v.get('url'),
                            )
                        ]
                    )
            NpcCorporation.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=[
                    'ceo_id',
                    'deleted',
                    'description_id',
                    'extent',
                    'has_player_personnel_manager',
                    'initial_price',
                    'member_limit',
                    'min_security',
                    'minimum_join_standing',
                    'name_id',
                    'public_shares',
                    'send_char_termination_message',
                    'shares',
                    'size',
                    'station_id',
                    'tax_rate',
                    'ticker_name',
                    'unique_name',
                    'allowed_member_races',
                    'corporation_trades',
                    'divisions',
                    'enemy_id',
                    'faction_id',
                    'friend_id',
                    'icon_id',
                    'investors',
                    'lp_offer_tables',
                    'main_activity_id',
                    'race_id',
                    'size_factor',
                    'solar_system_id',
                    'exchange_rates',
                    'secondary_activity_id',
                    'url',
                ],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading npcCorporations from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/npcCorporations.yaml',
            checksum=checksum,
        )

    def load_fsd_planet_resources(self) -> None:
        logger.info('Loading planetResources from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'planetResources')
        existing_checksum = self.local_checksum_lookup('fsd/planetResources.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('planetResources.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            PlanetResource(
                                id=k,
                                power=v.get('power'),
                                workforce=v.get('workforce'),
                                cycle_minutes=v.get('cycleMinutes'),
                                harvest_silo_max=v.get('harvestSiloMax'),
                                maturation_cycle_minutes=v.get(
                                    'maturationCycleMinutes'
                                ),
                                maturation_percent=v.get('maturationPercent'),
                                mature_silo_max=v.get('matureSiloMax'),
                                reagent_harvest_amount=v.get('reagentHarvestAmount'),
                                reagent_type_id=v.get('reagentTypeID'),
                            )
                        ]
                    )
            PlanetResource.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=[
                    'power',
                    'workforce',
                    'cycle_minutes',
                    'harvest_silo_max',
                    'maturation_cycle_minutes',
                    'maturation_percent',
                    'mature_silo_max',
                    'reagent_harvest_amount',
                    'reagent_type_id',
                ],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading planetResources from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/planetResources.yaml',
            checksum=checksum,
        )

    def load_fsd_planet_schematics(self) -> None:
        logger.info('Loading planetSchematics from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'planetSchematics')
        existing_checksum = self.local_checksum_lookup('fsd/planetSchematics.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info(
                'planetSchematics.yaml checksum matches existing, skipping load'
            )
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            PlanetSchematic(
                                id=k,
                                cycle_time=v.get('cycleTime'),
                                name_id=v.get('nameID'),
                                pins=v.get('pins'),
                                types=v.get('types'),
                            )
                        ]
                    )
            PlanetSchematic.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=['cycle_time', 'name_id', 'pins', 'types'],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading planetSchematics from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/planetSchematics.yaml',
            checksum=checksum,
        )

    def load_fsd_races(self) -> None:
        logger.info('Loading planetSchematics from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'races')
        existing_checksum = self.local_checksum_lookup('fsd/races.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('races.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            Race(
                                id=k,
                                description_id=v.get('descriptionID'),
                                icon_id=v.get('iconID'),
                                name_id=v.get('nameID'),
                                ship_type_id=v.get('shipTypeID'),
                                skills=v.get('skills'),
                            )
                        ]
                    )
            Race.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=[
                    'description_id',
                    'icon_id',
                    'name_id',
                    'ship_type_id',
                    'skills',
                ],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading races from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/races.yaml',
            checksum=checksum,
        )

    def load_research_agents(self) -> None:
        logger.info('Loading researchAgents from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'researchAgents')
        existing_checksum = self.local_checksum_lookup('fsd/researchAgents.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('researchAgents.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            ResearchAgent(
                                id=k,
                                skills=v.get('skills'),
                            )
                        ]
                    )
            ResearchAgent.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=['skills'],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading researchAgents from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/researchAgents.yaml',
            checksum=checksum,
        )

    def load_fsd_skin_licenses(self) -> None:
        logger.info('Loading skinLicenses from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'skinLicenses')
        existing_checksum = self.local_checksum_lookup('fsd/skinLicenses.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('skinLicenses.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            SkinLicense(
                                id=k,
                                duration=v.get('duration'),
                                license_type_id=v.get('licenseTypeID'),
                                skin_id=v.get('skinID'),
                                is_single_use=v.get('isSingleUse'),
                            )
                        ]
                    )
            SkinLicense.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=[
                    'duration',
                    'license_type_id',
                    'skin_id',
                    'is_single_use',
                ],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading skinLicenses from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/skinLicenses.yaml',
            checksum=checksum,
        )

    def load_fsd_skin_materials(self) -> None:
        logger.info('Loading skinMaterials from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'skinMaterials')
        existing_checksum = self.local_checksum_lookup('fsd/skinMaterials.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('skinMaterials.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            SkinMaterial(
                                id=k,
                                display_name_id=v.get('displayNameID'),
                                material_set_id=v.get('materialSetID'),
                                skin_material_id=v.get('skinMaterialID'),
                            )
                        ]
                    )
            SkinMaterial.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=[
                    'display_name_id',
                    'material_set_id',
                    'skin_material_id',
                ],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading skinMaterials from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/skinMaterials.yaml',
            checksum=checksum,
        )

    def load_fsd_skins(self) -> None:
        logger.info('Loading skins from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'skins')
        existing_checksum = self.local_checksum_lookup('fsd/skins.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('skins.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            Skin(
                                id=k,
                                allow_ccpdevs=v.get('allowCCPDevs'),
                                internal_name=v.get('internalName'),
                                skin_id=v.get('skinID'),
                                skin_material_id=v.get('skinMaterialID'),
                                types=v.get('types'),
                                visible_serenity=v.get('visibleSerenity'),
                                visible_tranquility=v.get('visibleTranquility'),
                                is_structure_skin=v.get('isStructureSkin', None),
                                skin_description=v.get('skinDescription'),
                            )
                        ]
                    )
            Skin.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=[
                    'allow_ccpdevs',
                    'internal_name',
                    'skin_id',
                    'skin_material_id',
                    'types',
                    'visible_serenity',
                    'visible_tranquility',
                    'is_structure_skin',
                    'skin_description',
                ],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading skins from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/skins.yaml',
            checksum=checksum,
        )

    def load_fsd_sovereignty_upgrades(self) -> None:
        logger.info('Loading sovereignty upgrades from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'sovereigntyUpgrades')
        existing_checksum = self.local_checksum_lookup('fsd/sovereigntyUpgrades.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info(
                'sovereigntyUpgrades.yaml checksum matches existing, skipping load'
            )
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            SovereigntyUpgrade(
                                id=k,
                                fuel_hourly_upkeep=v.get('fuel_hourly_upkeep'),
                                fuel_startup_cost=v.get('fuel_startup_cost'),
                                fuel_type_id=v.get('fuel_type_id'),
                                mutually_exclusive_group=v.get(
                                    'mutually_exclusive_group'
                                ),
                                power_allocation=v.get('power_allocation'),
                                workforce_allocation=v.get('workforce_allocation'),
                            )
                        ]
                    )
            SovereigntyUpgrade.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=[
                    'fuel_hourly_upkeep',
                    'fuel_startup_cost',
                    'fuel_type_id',
                    'mutually_exclusive_group',
                    'power_allocation',
                    'workforce_allocation',
                ],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading sovereignty upgrades from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/sovereigntyUpgrades.yaml',
            checksum=checksum,
        )

    def load_fsd_station_operations(self) -> None:
        logger.info('Loading station operations from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'stationOperations')
        existing_checksum = self.local_checksum_lookup('fsd/stationOperations.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info(
                'stationOperations.yaml checksum matches existing, skipping load'
            )
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            StationOperation(
                                id=k,
                                activity_id=v.get('activityID'),
                                border=v.get('border'),
                                corridor=v.get('corridor'),
                                description_id=v.get('descriptionID'),
                                fringe=v.get('fringe'),
                                hub=v.get('hub'),
                                manufacturing_factor=v.get('manufacturingFactor'),
                                operation_name_id=v.get('operationNameID'),
                                ratio=v.get('ratio'),
                                research_factor=v.get('researchFactor'),
                                services=v.get('services'),
                                station_types=v.get('stationTypes'),
                            )
                        ]
                    )
            StationOperation.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=[
                    'activity_id',
                    'border',
                    'corridor',
                    'description_id',
                    'fringe',
                    'hub',
                    'manufacturing_factor',
                    'operation_name_id',
                    'ratio',
                    'research_factor',
                    'services',
                    'station_types',
                ],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading station operations from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/stationOperations.yaml',
            checksum=checksum,
        )

    def load_fsd_station_services(self) -> None:
        logger.info('Loading station services from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'stationServices')
        existing_checksum = self.local_checksum_lookup('fsd/stationServices.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('stationServices.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            StationService(
                                id=k,
                                service_name_id=v.get('serviceNameID'),
                                description_id=v.get('descriptionID', None),
                            )
                        ]
                    )
            StationService.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=[
                    'service_name_id',
                    'description_id',
                ],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading station services from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/stationServices.yaml',
            checksum=checksum,
        )

    def load_fsd_tournament_rule_set(self) -> None:
        logger.info('Loading tournament rule set from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'tournamentRuleSets')
        existing_checksum = self.local_checksum_lookup('fsd/tournamentRuleSets.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info(
                'tournamentRuleSets.yaml checksum matches existing, skipping load'
            )
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for i in data:
                    records.extend(
                        [
                            TournamentRuleSet(
                                banned=i.get('banned'),
                                maximum_pilots_match=i.get('maximumPilotsMatch'),
                                maximum_points_match=i.get('maximumPointsMatch'),
                                points=i.get('points'),
                                rule_set_id=i.get('ruleSetID'),
                                rule_set_name=i.get('ruleSetName'),
                            )
                        ]
                    )
            TournamentRuleSet.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=[
                    'banned',
                    'maximum_pilots_match',
                    'maximum_points_match',
                    'points',
                    'rule_set_name',
                ],
                unique_fields=['rule_set_id'],
            )
        except Exception:
            logger.exception('Failed loading tournament rule set from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/tournamentRuleSet.yaml',
            checksum=checksum,
        )

    def load_fsd_type_dogma(self) -> None:
        logger.info('Loading type dogma from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'typeDogma')
        existing_checksum = self.local_checksum_lookup('fsd/typeDogma.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('typeDogma.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            TypeDogma(
                                id=k,
                                dogma_attributes=v.get('dogmaAttributes'),
                                dogma_effects=v.get('dogmaEffects'),
                            )
                        ]
                    )
            TypeDogma.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=[
                    'dogma_attributes',
                    'dogma_effects',
                ],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading type dogma from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/typeDogma.yaml',
            checksum=checksum,
        )

    def load_fsd_type_materials(self) -> None:
        logger.info('Loading type materials from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'typeMaterials')
        existing_checksum = self.local_checksum_lookup('fsd/typeMaterials.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('typeMaterials.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            TypeMaterial(
                                id=k,
                                materials=v.get('materials'),
                            )
                        ]
                    )
            TypeMaterial.objects.bulk_create(
                records,
                update_conflicts=True,
                update_fields=[
                    'materials',
                ],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading type materials from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/typeMaterials.yaml',
            checksum=checksum,
        )

    def load_fsd_types(self) -> None:
        logger.info('Loading types from FSD data...')
        json_file, yaml_file = self.build_file_path('fsd', 'types')
        existing_checksum = self.local_checksum_lookup('fsd/types.yaml')
        checksum = self.get_file_checksum(yaml_file)
        if existing_checksum == checksum and existing_checksum != '':
            logger.info('types.yaml checksum matches existing, skipping load')
            return
        try:
            records = []
            with Path(json_file).open() as f:
                data = json.load(f)
                for k, v in data.items():
                    records.extend(
                        [
                            Type(
                                id=k,
                                group_id=v.get('groupID'),
                                mass=v.get('mass'),
                                name=v.get('name'),
                                portion_size=v.get('portionSize'),
                                published=v.get('published'),
                                volume=v.get('volume'),
                                radius=v.get('radius'),
                                description=v.get('description'),
                                graphic_id=v.get('graphicID'),
                                sound_id=v.get('soundID'),
                                icon_id=v.get('iconID'),
                                race_id=v.get('raceID'),
                                sof_faction_name=v.get('sofFactionName'),
                                base_price=v.get('basePrice'),
                                market_group_id=v.get('marketGroupID'),
                                capacity=v.get('capacity'),
                                meta_group_id=v.get('metaGroupID'),
                                variation_parent_type_id=v.get('variationParentTypeID'),
                                faction_id=v.get('factionID'),
                                masteries=v.get('masteries'),
                                traits=v.get('traits'),
                                sof_material_set_id=v.get('sofMaterialSetID'),
                            )
                        ]
                    )
                Type.objects.bulk_create(
                    records,
                    update_conflicts=True,
                    update_fields=[
                        'group_id',
                        'mass',
                        'name',
                        'portion_size',
                        'published',
                        'volume',
                        'radius',
                        'description',
                        'graphic_id',
                        'sound_id',
                        'icon_id',
                        'race_id',
                        'sof_faction_name',
                        'base_price',
                        'market_group_id',
                        'capacity',
                        'meta_group_id',
                        'variation_parent_type_id',
                        'faction_id',
                        'masteries',
                        'traits',
                        'sof_material_set_id',
                    ],
                    unique_fields=['id'],
                )
        except Exception:
            logger.exception('Failed loading types from %s', json_file)
            return
        Checksum.objects.update_or_create(
            name='fsd/types.yaml',
            checksum=checksum,
        )

    def load_universe_regions(self) -> None:
        logger.info('Loading regions from Universe data...')
        region_files = Path(self.workspace_dir / 'universe').rglob('region.yaml')
        for region_file in region_files:
            json_file = region_file.with_suffix('.json')
            yaml_file = region_file.with_suffix('.yaml')
            checksum_name = str(yaml_file).split(f'{self.workspace_dir}/')[1]
            existing_checksum = self.local_checksum_lookup(checksum_name)
            checksum = self.get_file_checksum(yaml_file)
            if existing_checksum == checksum and existing_checksum != '':
                logger.info('regions.yaml checksum matches existing, skipping load')
                return
            try:
                with Path(json_file).open() as f:
                    data = json.load(f)
                    Region(
                        region_id=data.get('regionID'),
                        name_id=data.get('nameID'),
                        nebula=data.get('nebula'),
                        wormhole_class_id=data.get('wormholeClassID'),
                        description_id=data.get('descriptionID'),
                        faction_id=data.get('factionID'),
                        center=data.get('center'),
                        max=data.get('max'),
                        min=data.get('min'),
                    ).save()
            except Exception:
                logger.exception('Failed loading regions from %s', json_file)
                return
            Checksum.objects.update_or_create(
                name=checksum_name,
                checksum=checksum,
            )

    def load_universe_constellations(self) -> None:
        logger.info('Loading constellations from Universe data...')
        constellation_files = Path(self.workspace_dir / 'universe').rglob(
            'constellation.yaml'
        )
        for constellation_file in constellation_files:
            json_file = constellation_file.with_suffix('.json')
            yaml_file = constellation_file.with_suffix('.yaml')
            checksum_name = str(yaml_file).split(f'{self.workspace_dir}/')[1]
            existing_checksum = self.local_checksum_lookup(checksum_name)
            checksum = self.get_file_checksum(yaml_file)
            if existing_checksum == checksum and existing_checksum != '':
                logger.info(
                    'constellations.yaml checksum matches existing, skipping load'
                )
                return
            try:
                with Path(json_file).open() as f:
                    data = json.load(f)
                    Constellation(
                        constellation_id=data.get('constellationID'),
                        name_id=data.get('nameID'),
                        radius=data.get('radius'),
                        center=data.get('center'),
                        max=data.get('max'),
                        min=data.get('min'),
                    ).save()
            except Exception:
                logger.exception('Failed loading constellations from %s', json_file)
                return
            Checksum.objects.update_or_create(
                name=checksum_name,
                checksum=checksum,
            )

    def load_universe_solar_systems(self) -> None:
        logger.info('Loading solar systems from Universe data...')
        solar_system_files = Path(self.workspace_dir / 'universe').rglob(
            'solarsystem.yaml'
        )
        solar_system_records = []
        planet_records = []
        moon_records = []
        asteroid_belt_records = []
        star_records = []
        try:
            for solar_system_file in solar_system_files:
                json_file = solar_system_file.with_suffix('.json')
                yaml_file = solar_system_file.with_suffix('.yaml')
                checksum_name = str(yaml_file).split(f'{self.workspace_dir}/')[1]
                existing_checksum = self.local_checksum_lookup(checksum_name)
                checksum = self.get_file_checksum(yaml_file)
                if existing_checksum == checksum and existing_checksum != '':
                    logger.info(
                        'solarsystem.yaml checksum matches existing, skipping load'
                    )
                    return
                try:
                    with Path(json_file).open() as f:
                        data = json.load(f)
                        # Load base solar system data
                        solar_system_records.extend(
                            [
                                SolarSystem(
                                    solar_system_id=data.get('solarSystemID'),
                                    border=data.get('border'),
                                    center=data.get('center'),
                                    corridor=data.get('corridor'),
                                    fringe=data.get('fringe'),
                                    hub=data.get('hub'),
                                    international=data.get('international'),
                                    luminosity=data.get('luminosity'),
                                    max=data.get('max'),
                                    min=data.get('min'),
                                    radius=data.get('radius'),
                                    regional=data.get('regional'),
                                    security=data.get('security'),
                                    solar_system_name_id=data.get('solarSystemNameID'),
                                    sun_type_id=data.get('sunTypeID'),
                                    wormhole_class_id=data.get('wormholeClassID'),
                                )
                            ]
                        )
                        # load star data
                        star = data.get('star', None)
                        if star:
                            star_records.append(
                                Star(
                                    id=star.get('id'),
                                    radius=star.get('radius'),
                                    statistics=star.get('statistics'),
                                    type_id=star.get('typeID'),
                                )
                            )
                        # load planet data
                        planets = data.get('planets', {})
                        for pk, pv in planets.items():
                            planet_records.extend(
                                [
                                    Planet(
                                        id=pk,
                                        celestial_index=pv.get('celestialIndex'),
                                        planet_attributes=pv.get('planetAttributes'),
                                        position=pv.get('position'),
                                        radius=pv.get('radius'),
                                        statistics=pv.get('statistics'),
                                        type_id=pv.get('typeID'),
                                        npc_stations=pv.get('npcStations'),
                                        planet_name_id=pv.get('planetNameID'),
                                    )
                                ]
                            )
                            # load moon data
                            moons = pv.get('moons', {})
                            for mk, mv in moons.items():
                                moon_records.extend(
                                    [
                                        Moon(
                                            id=mk,
                                            planet_attributes=mv.get(
                                                'planetAttributes'
                                            ),
                                            position=mv.get('position'),
                                            radius=mv.get('radius'),
                                            statistics=mv.get('statistics'),
                                            type_id=mv.get('typeID'),
                                            npc_stations=mv.get('npcStations'),
                                            moon_name_id=mv.get('moonNameID'),
                                        )
                                    ]
                                )
                            # load asteroid belt data
                            asteroid_belt = pv.get('asteroidBelt', {})
                            for ak, av in asteroid_belt.items():
                                asteroid_belt_records.extend(
                                    [
                                        AsteroidBelt(
                                            id=ak,
                                            position=av.get('position'),
                                            statistics=av.get('statistics'),
                                            type_id=av.get('typeID'),
                                            asteroid_belt_name_id=av.get(
                                                'asteroidBeltNameID'
                                            ),
                                        )
                                    ]
                                )
                except Exception:
                    logger.exception('Failed loading solar systems from %s', json_file)
                    return
                Checksum.objects.update_or_create(
                    name=checksum_name,
                    checksum=checksum,
                )
            SolarSystem.objects.bulk_create(
                solar_system_records,
                update_conflicts=True,
                update_fields=[
                    'border',
                    'center',
                    'corridor',
                    'fringe',
                    'hub',
                    'international',
                    'luminosity',
                    'max',
                    'min',
                    'radius',
                    'regional',
                    'security',
                    'solar_system_name_id',
                    'sun_type_id',
                    'wormhole_class_id',
                ],
                unique_fields=['solar_system_id'],
            )
            Star.objects.bulk_create(
                star_records,
                update_conflicts=True,
                update_fields=[
                    'radius',
                    'statistics',
                    'type_id',
                ],
                unique_fields=['id'],
            )
            Planet.objects.bulk_create(
                planet_records,
                update_conflicts=True,
                update_fields=[
                    'celestial_index',
                    'planet_attributes',
                    'position',
                    'radius',
                    'statistics',
                    'type_id',
                    'npc_stations',
                    'planet_name_id',
                ],
                unique_fields=['id'],
            )
            Moon.objects.bulk_create(
                moon_records,
                update_conflicts=True,
                update_fields=[
                    'planet_attributes',
                    'position',
                    'radius',
                    'statistics',
                    'type_id',
                    'npc_stations',
                    'moon_name_id',
                ],
                unique_fields=['id'],
            )
            AsteroidBelt.objects.bulk_create(
                asteroid_belt_records,
                update_conflicts=True,
                update_fields=[
                    'asteroid_belt_name_id',
                    'position',
                    'statistics',
                    'type_id',
                ],
                unique_fields=['id'],
            )
        except Exception:
            logger.exception('Failed loading solar systems batch')
            return

    def load_universe_lookups(self) -> None:
        # Iterate over the universe subdirectories
        universe_dir = Path(self.workspace_dir / 'universe')
        for subdir in universe_dir.iterdir():
            if subdir.is_dir() and subdir.name != 'landmarks':
                for region_dir in subdir.iterdir():
                    if region_dir.is_dir():
                        with region_dir.joinpath('region.json').open() as f:
                            region_id = json.load(f).get('regionID')
                        for constellation_dir in region_dir.iterdir():
                            if constellation_dir.is_dir():
                                with constellation_dir.joinpath(
                                    'constellation.json'
                                ).open() as f:
                                    constellation_id = json.load(f).get(
                                        'constellationID'
                                    )
                                for solar_system_file in constellation_dir.rglob(
                                    'solarsystem.json'
                                ):
                                    with solar_system_file.open() as f:
                                        solar_system_data = json.load(f)
                                        solar_system_id = solar_system_data.get(
                                            'solarSystemID'
                                        )
                                        planets = solar_system_data.get('planets', {})
                                        for pk, pv in planets.items():
                                            moons = pv.get('moons', {}).keys()
                                            asteroid_belts = pv.get(
                                                'asteroidBelts', {}
                                            ).keys()
                                            ## Create the lookup mappings
                                            UniverseLookup.objects.update_or_create(
                                                region_id=region_id,
                                                constellation_id=constellation_id,
                                                solar_system_id=solar_system_id,
                                                planet_id=pk,
                                                moons=[int(moon) for moon in moons],
                                                asteroid_belts=[
                                                    int(asteroid_belt)
                                                    for asteroid_belt in asteroid_belts
                                                ],
                                            )
        logger.info('Universe lookups loaded successfully.')

    @deprecated('moons and astroidbelts are now being stored in jsonb fields')
    def create_universe_lookup_mappings(  # noqa: PLR0913
        self,
        region_id,
        constellation_id,
        solar_system_id,
        planet_id,
        moons,
        asteroid_belts,
    ) -> list[dict[str, int | None]]:
        results = []
        max_len = max(len(moons), len(asteroid_belts))
        for i in range(max_len):
            result = {
                'region_id': region_id,
                'constellation_id': constellation_id,
                'solar_system_id': solar_system_id,
                'planet_id': planet_id,
                'moon_id': moons[i] if i < len(moons) else None,
                'asteroid_belt_id': asteroid_belts[i]
                if i < len(asteroid_belts)
                else None,
            }
            results.append(result)
        return results

    def handle(self, *args: Any, **options: Any) -> None:  # noqa: PLR0915
        # Setup the workspace
        self.setup_workspace()
        self.get_local_checksums()
        self.get_remote_checksums()
        # Validate and Download the SDE data
        self.download_sde(force_download=options.get('force_download', False))
        if not Path(self.workspace_dir / '.sde_extracted').exists():
            self.extract_sde()
        # Convert extracted YAML files to JSON (optional script)
        if (
            not options.get('skip_yaml_to_json', False)
            or not Path(self.workspace_dir / '.convert_to_json_done').is_file()
        ):
            self.run_yaml_to_json_conversion()
        if options.get('download_only', False):
            logger.info('Download-only flag set, skipping further processing')
            return
        # Load data into the database
        ## Load BSD data
        self.load_bsd_inv_flags()
        self.load_bsd_inv_items()
        self.load_bsd_inv_names()
        self.load_bsd_inv_positions()
        self.load_bsd_inv_unique_names()
        self.load_bsd_sta_stations()
        ## Load FSD data
        self.load_fsd_agents()
        self.load_fsd_agents_in_space()
        self.load_fsd_ancestries()
        self.load_fsd_bloodlines()
        self.load_fsd_blueprints()
        self.load_fsd_categories()
        self.load_fsd_certificates()
        self.load_fsd_character_attributes()
        self.load_fsd_contraband_types()
        self.load_fsd_control_tower_resources()
        self.load_fsd_corporation_activities()
        self.load_fsd_dogma_attribute_categories()
        self.load_fsd_dogma_attributes()
        self.load_fsd_dogma_effects()
        self.load_fsd_factions()
        self.load_fsd_graphic_ids()
        self.load_fsd_groups()
        self.load_fsd_icon_ids()
        self.load_fsd_market_groups()
        self.load_fsd_meta_groups()
        self.load_fsd_npc_corporation_divisions()
        self.load_fsd_npc_corporations()
        self.load_fsd_planet_resources()
        self.load_fsd_planet_schematics()
        self.load_fsd_races()
        self.load_research_agents()
        self.load_fsd_skin_licenses()
        self.load_fsd_skin_materials()
        self.load_fsd_skins()
        self.load_fsd_sovereignty_upgrades()
        self.load_fsd_station_operations()
        self.load_fsd_station_services()
        self.load_fsd_tournament_rule_set()
        self.load_fsd_type_dogma()
        self.load_fsd_type_materials()
        self.load_fsd_types()
        # Load Universe data
        self.load_universe_regions()
        self.load_universe_constellations()
        self.load_universe_solar_systems()
        # Load Universe Lookups
        self.load_universe_lookups()

        logger.info('SDE processing completed')
