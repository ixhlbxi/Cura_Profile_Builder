#!/usr/bin/env python3
"""
Cura Profile Builder v1.0.0
===========================
Create importable .curaprofile files for Cura slicer.

Build custom quality profiles from:
  - Preset templates (PLA, PETG, ABS, TPU, ASA × draft/normal/fine/ultra)
  - Previous extraction JSON (from Cura Profile Extractor)
  - Manual setting specification

Features:
  - Auto-detects Cura install and AppData paths
  - Auto-detects setting_version from existing Cura configs
  - Validates settings against fdmprinter.def.json constraints
  - Separates global vs per-extruder settings automatically
  - Generates Cura-compatible .curaprofile ZIP files
  - GUI (default) or CLI mode
  - Works with any printer manufacturer

Usage:
  python cura_profile_builder.py                    # GUI mode
  python cura_profile_builder.py --help             # Help
  
  # Build from preset
  python cura_profile_builder.py --preset PLA/normal --definition creality_ender3pro
  
  # Build from extraction JSON
  python cura_profile_builder.py --from-json my_extraction.json --name "My Profile"

Companion tool: Cura Profile Extractor (extracts settings to JSON)
  https://github.com/ixhlbxi/Cura_Profile_Extractor

Author: Brian's 3D Printer Project
License: MIT
"""

import argparse
import configparser
import io
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from urllib.parse import unquote, quote
import zipfile

# Tkinter is optional - only needed for GUI mode
try:
    import tkinter as tk
    from tkinter import ttk, filedialog, scrolledtext, messagebox
    TKINTER_AVAILABLE = True
except ImportError:
    TKINTER_AVAILABLE = False

__version__ = "1.0.0"


# =============================================================================
# USER OVERRIDES — Power User Fallback Configuration
# =============================================================================
#
# If auto-detection fails, uncomment and modify these values.
# They take precedence over auto-detection when set to non-None values.
#
# FINDING YOUR PATHS:
#   - Install path: Where Cura.exe lives. Look for "share/cura/resources" subfolder.
#   - AppData path: Your user settings. Contains "cura.cfg" and "machine_instances/".
#   - Windows: Usually %APPDATA%\cura\<version>
#   - Linux: Usually ~/.config/cura/<version> or ~/.local/share/cura/<version>
#   - Mac: Usually ~/Library/Application Support/cura/<version>
#
# -----------------------------------------------------------------------------

# Path to Cura installation directory
# USER_INSTALL_PATH_OVERRIDE = r"C:\Program Files\UltiMaker Cura 5.11.0"
USER_INSTALL_PATH_OVERRIDE = None

# Path to Cura user data directory
# USER_APPDATA_PATH_OVERRIDE = r"C:\Users\YourName\AppData\Roaming\cura\5.11"
USER_APPDATA_PATH_OVERRIDE = None

# Override setting_version if auto-detection fails
# Cura 5.x typically uses setting_version 20-23
# USER_SETTING_VERSION_OVERRIDE = 23
USER_SETTING_VERSION_OVERRIDE = None

# -----------------------------------------------------------------------------
# END USER OVERRIDES
# =============================================================================


# =============================================================================
# Preset Templates
# =============================================================================

MATERIAL_PRESETS = {
    "PLA": {
        "description": "Standard PLA - good all-around starter settings",
        "settings": {
            "material_print_temperature": 200,
            "material_bed_temperature": 60,
            "speed_print": 50,
            "retraction_amount": 0.8,
            "retraction_speed": 45,
            "cool_fan_speed": 100,
        }
    },
    "PETG": {
        "description": "PETG - higher temps, slower speeds, less cooling",
        "settings": {
            "material_print_temperature": 240,
            "material_bed_temperature": 80,
            "speed_print": 40,
            "retraction_amount": 1.0,
            "retraction_speed": 35,
            "cool_fan_speed": 50,
        }
    },
    "ABS": {
        "description": "ABS - high temps, minimal cooling, enclosure recommended",
        "settings": {
            "material_print_temperature": 240,
            "material_bed_temperature": 100,
            "speed_print": 50,
            "retraction_amount": 0.8,
            "retraction_speed": 45,
            "cool_fan_speed": 0,
        }
    },
    "TPU": {
        "description": "TPU/Flexible - slow and careful, direct drive recommended",
        "settings": {
            "material_print_temperature": 230,
            "material_bed_temperature": 60,
            "speed_print": 25,
            "retraction_amount": 2.0,
            "retraction_speed": 25,
            "cool_fan_speed": 100,
        }
    },
    "ASA": {
        "description": "ASA - like ABS but better UV resistance",
        "settings": {
            "material_print_temperature": 260,
            "material_bed_temperature": 100,
            "speed_print": 50,
            "retraction_amount": 0.8,
            "retraction_speed": 45,
            "cool_fan_speed": 30,
        }
    },
}

QUALITY_PRESETS = {
    "draft": {
        "description": "Fast draft - 0.28mm layers, quick prints",
        "settings": {
            "layer_height": 0.28,
            "layer_height_0": 0.28,
        }
    },
    "normal": {
        "description": "Standard quality - 0.2mm layers, balanced",
        "settings": {
            "layer_height": 0.2,
            "layer_height_0": 0.2,
        }
    },
    "fine": {
        "description": "Fine quality - 0.12mm layers, detailed prints",
        "settings": {
            "layer_height": 0.12,
            "layer_height_0": 0.2,
        }
    },
    "ultra": {
        "description": "Ultra fine - 0.08mm layers, maximum detail",
        "settings": {
            "layer_height": 0.08,
            "layer_height_0": 0.16,
        }
    },
}


# =============================================================================
# Path Detection
# =============================================================================

def find_cura_install_path() -> Optional[Path]:
    """Auto-detect Cura installation directory."""
    if USER_INSTALL_PATH_OVERRIDE:
        override_path = Path(USER_INSTALL_PATH_OVERRIDE)
        if override_path.exists():
            return override_path
        print(f"WARNING: USER_INSTALL_PATH_OVERRIDE path not found: {USER_INSTALL_PATH_OVERRIDE}")
    
    search_paths = []
    
    if sys.platform == "win32":
        search_paths = [
            Path(os.environ.get("PROGRAMFILES", "C:/Program Files")),
            Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")),
            Path(os.environ.get("LOCALAPPDATA", "")),
        ]
    elif sys.platform == "linux":
        home = Path.home()
        search_paths = [
            home / ".local" / "share",
            Path("/usr/share"),
            Path("/opt"),
        ]
    elif sys.platform == "darwin":  # macOS
        home = Path.home()
        search_paths = [
            home / "Applications",
            Path("/Applications"),
        ]
    
    candidates = []
    for base in search_paths:
        if not base.exists():
            continue
        try:
            for item in base.iterdir():
                if item.is_dir() and "cura" in item.name.lower():
                    if (item / "share" / "cura" / "resources").exists():
                        match = re.search(r'(\d+\.\d+\.?\d*)', item.name)
                        version = match.group(1) if match else "0.0.0"
                        candidates.append((version, item))
        except PermissionError:
            continue
    
    if not candidates:
        return None
    
    # Return newest version
    candidates.sort(key=lambda x: [int(p) for p in x[0].split('.')[:3]], reverse=True)
    return candidates[0][1]


def find_cura_appdata_path() -> Optional[Path]:
    """Auto-detect Cura AppData directory."""
    if USER_APPDATA_PATH_OVERRIDE:
        override_path = Path(USER_APPDATA_PATH_OVERRIDE)
        if override_path.exists():
            return override_path
        print(f"WARNING: USER_APPDATA_PATH_OVERRIDE path not found: {USER_APPDATA_PATH_OVERRIDE}")
    
    home = Path.home()
    search_bases = []
    
    if sys.platform == "win32":
        appdata = Path(os.environ.get("APPDATA", ""))
        if appdata.exists():
            search_bases.append(appdata / "cura")
    elif sys.platform == "linux":
        search_bases = [
            home / ".config" / "cura",
            home / ".local" / "share" / "cura",
        ]
    elif sys.platform == "darwin":
        search_bases.append(home / "Library" / "Application Support" / "cura")
    
    versions = []
    for base in search_bases:
        if not base.exists():
            continue
        try:
            for item in base.iterdir():
                if item.is_dir() and re.match(r'^\d+\.\d+', item.name):
                    if (item / "cura.cfg").exists() or (item / "machine_instances").exists():
                        versions.append(item)
        except PermissionError:
            continue
    
    if not versions:
        return None
    
    versions.sort(key=lambda x: [int(p) for p in x.name.split('.')[:2]], reverse=True)
    return versions[0]


# =============================================================================
# File Parsers
# =============================================================================

def parse_cfg_file(filepath: Path) -> Dict[str, Any]:
    """Parse Cura .cfg or .inst.cfg file (INI-style format)."""
    result = {
        "_filepath": str(filepath),
        "_filename": filepath.name,
    }
    
    if not filepath.exists():
        result["_error"] = "File not found"
        return result
    
    try:
        config = configparser.ConfigParser(interpolation=None)
        config.read(filepath, encoding='utf-8')
        
        for section in config.sections():
            result[section] = dict(config[section])
        
        return result
    except Exception as e:
        result["_error"] = str(e)
        return result


def parse_def_json(filepath: Path) -> Dict[str, Any]:
    """Parse Cura .def.json definition file."""
    result = {
        "_filepath": str(filepath),
        "_filename": filepath.name,
    }
    
    if not filepath.exists():
        result["_error"] = "File not found"
        return result
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        result.update(data)
        return result
    except Exception as e:
        result["_error"] = str(e)
        return result


def extract_settings_from_def(def_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Recursively extract all settings from a definition file.
    Returns {setting_key: {default_value, type, description, ...}}
    """
    settings = {}
    
    def recurse(node: Dict[str, Any], path: str = "", category: str = ""):
        current_category = category
        if "type" in node and node["type"] == "category":
            current_category = path
        
        if "children" in node:
            for key, child in node["children"].items():
                recurse(child, key, current_category)
        
        # Extract setting properties
        if "type" in node and node["type"] != "category":
            setting_info = {"_category": current_category}
            for prop in ["default_value", "value", "type", "description", "unit", 
                         "minimum_value", "maximum_value", "minimum_value_warning",
                         "maximum_value_warning", "enabled", "settable_per_mesh",
                         "settable_per_extruder", "settable_globally", "options", "label"]:
                if prop in node:
                    setting_info[prop] = node[prop]
            if setting_info:
                settings[path] = setting_info
    
    if "settings" in def_data:
        for category_key, category in def_data["settings"].items():
            recurse(category, category_key, category_key)
    
    if "overrides" in def_data:
        for key, override in def_data["overrides"].items():
            if key not in settings:
                settings[key] = {}
            settings[key].update(override)
            settings[key]["_source"] = def_data.get("_filename", "unknown")
    
    return settings


# =============================================================================
# Setting Metadata & Validation
# =============================================================================

class SettingMetadata:
    """
    Manages setting definitions from fdmprinter.def.json.
    Provides type info, validation, and categorization.
    """
    
    def __init__(self, install_path: Path):
        self.install_path = install_path
        self.settings: Dict[str, Dict[str, Any]] = {}
        self.categories: Dict[str, List[str]] = {}
        self.loaded = False
    
    def load(self) -> bool:
        """Load setting metadata from fdmprinter.def.json."""
        fdmprinter_path = self.install_path / "share" / "cura" / "resources" / "definitions" / "fdmprinter.def.json"
        
        if not fdmprinter_path.exists():
            return False
        
        def_data = parse_def_json(fdmprinter_path)
        if "_error" in def_data:
            return False
        
        self.settings = extract_settings_from_def(def_data)
        
        # Build category index
        for key, info in self.settings.items():
            category = info.get("_category", "other")
            if category not in self.categories:
                self.categories[category] = []
            self.categories[category].append(key)
        
        self.loaded = True
        return True
    
    def get_type(self, setting_key: str) -> str:
        """Get the type of a setting."""
        if setting_key not in self.settings:
            return "unknown"
        return self.settings[setting_key].get("type", "unknown")
    
    def get_default(self, setting_key: str) -> Any:
        """Get the default value of a setting."""
        if setting_key not in self.settings:
            return None
        return self.settings[setting_key].get("default_value")
    
    def get_label(self, setting_key: str) -> str:
        """Get the human-readable label for a setting."""
        if setting_key not in self.settings:
            return setting_key
        return self.settings[setting_key].get("label", setting_key)
    
    def get_category(self, setting_key: str) -> str:
        """Get the category of a setting."""
        if setting_key not in self.settings:
            return "unknown"
        return self.settings[setting_key].get("_category", "unknown")
    
    def is_per_extruder(self, setting_key: str) -> bool:
        """Check if setting should go in extruder config vs global."""
        if setting_key not in self.settings:
            return False
        return self.settings[setting_key].get("settable_per_extruder", False)
    
    def validate_value(self, setting_key: str, value: Any) -> Tuple[bool, str]:
        """
        Validate a setting value against its constraints.
        Returns (is_valid, error_or_warning_message).
        """
        if setting_key not in self.settings:
            return True, ""  # Unknown settings pass (might be custom)
        
        info = self.settings[setting_key]
        setting_type = info.get("type", "unknown")
        
        # Type checking
        try:
            if setting_type == "int":
                if not isinstance(value, int) or isinstance(value, bool):
                    value = int(value)
            elif setting_type == "float":
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    value = float(value)
            elif setting_type == "bool":
                if not isinstance(value, bool):
                    if isinstance(value, str):
                        value = value.lower() in ("true", "1", "yes")
                    else:
                        value = bool(value)
            elif setting_type == "enum":
                options = info.get("options", {})
                if value not in options:
                    return False, f"Invalid option '{value}'. Valid: {list(options.keys())}"
        except (ValueError, TypeError) as e:
            return False, f"Type conversion failed: {e}"
        
        # Range checking for numeric types
        if setting_type in ("int", "float"):
            min_val = info.get("minimum_value")
            max_val = info.get("maximum_value")
            min_warn = info.get("minimum_value_warning")
            max_warn = info.get("maximum_value_warning")
            
            if min_val is not None and value < min_val:
                return False, f"Value {value} below minimum {min_val}"
            if max_val is not None and value > max_val:
                return False, f"Value {value} above maximum {max_val}"
            
            # Warnings (valid but noted)
            warnings = []
            if min_warn is not None and value < min_warn:
                warnings.append(f"below recommended {min_warn}")
            if max_warn is not None and value > max_warn:
                warnings.append(f"above recommended {max_warn}")
            
            if warnings:
                return True, f"Value {value} " + ", ".join(warnings)
        
        return True, ""
    
    def get_all_categories(self) -> List[str]:
        """Get list of all setting categories."""
        return sorted(self.categories.keys())
    
    def get_settings_in_category(self, category: str) -> List[str]:
        """Get all setting keys in a category."""
        return self.categories.get(category, [])
    
    def format_value_for_cfg(self, setting_key: str, value: Any) -> str:
        """Format a value for writing to .inst.cfg file."""
        setting_type = self.get_type(setting_key)
        
        if setting_type == "bool":
            return "True" if value else "False"
        elif setting_type in ("str", "extruder"):
            # Escape newlines in strings (especially G-code)
            if isinstance(value, str):
                return value.replace("\n", "\\n").replace("\t", "\\t")
            return str(value)
        else:
            return str(value)


# =============================================================================
# Cura Profile Builder
# =============================================================================

class CuraBuilder:
    """
    Builds .curaprofile files that can be imported into Cura.
    
    .curaprofile structure:
        profile_name.curaprofile (ZIP)
        ├── profile_name.inst.cfg           # Global quality settings
        └── profile_name_extruder_0.inst.cfg  # Per-extruder settings
    """
    
    def __init__(self, install_path: str, appdata_path: str, log_callback=None):
        self.install_path = Path(install_path) if install_path else None
        self.appdata_path = Path(appdata_path) if appdata_path else None
        self.log = log_callback or print
        
        # Metadata for validation
        self.metadata = SettingMetadata(self.install_path) if self.install_path else None
        
        # Auto-detected values
        self.setting_version: Optional[int] = None
        self.cura_version: str = "unknown"
        self.available_definitions: List[str] = []
    
    def initialize(self) -> Tuple[bool, List[str]]:
        """
        Initialize the builder by loading metadata and detecting versions.
        Returns (success, errors).
        """
        errors = []
        
        if not self.install_path or not self.install_path.exists():
            errors.append(f"Install path not found: {self.install_path}")
            return False, errors
        
        # Load setting metadata
        if self.metadata and not self.metadata.load():
            errors.append("Failed to load fdmprinter.def.json - validation disabled")
        else:
            self.log(f"  Loaded {len(self.metadata.settings)} setting definitions")
        
        # Detect setting_version
        self.setting_version = self._detect_setting_version()
        if self.setting_version:
            self.log(f"  Detected setting_version: {self.setting_version}")
        else:
            errors.append("Could not detect setting_version - using default 23")
            self.setting_version = 23
        
        # Detect Cura version from path
        match = re.search(r'(\d+\.\d+\.?\d*)', str(self.install_path))
        if match:
            self.cura_version = match.group(1)
            self.log(f"  Cura version: {self.cura_version}")
        
        # Discover available machine definitions
        self.available_definitions = self._discover_definitions()
        self.log(f"  Found {len(self.available_definitions)} machine definitions")
        
        return len(errors) == 0 or (self.metadata and self.metadata.loaded), errors
    
    def _detect_setting_version(self) -> Optional[int]:
        """Auto-detect setting_version from existing Cura configs."""
        if USER_SETTING_VERSION_OVERRIDE:
            return USER_SETTING_VERSION_OVERRIDE
        
        if not self.appdata_path or not self.appdata_path.exists():
            return None
        
        # Check quality_changes folder
        quality_changes = self.appdata_path / "quality_changes"
        if quality_changes.exists():
            for cfg_file in quality_changes.glob("*.inst.cfg"):
                cfg = parse_cfg_file(cfg_file)
                if "metadata" in cfg:
                    sv = cfg["metadata"].get("setting_version")
                    if sv:
                        try:
                            return int(sv)
                        except ValueError:
                            continue
        
        # Check extruder configs
        extruders = self.appdata_path / "extruders"
        if extruders.exists():
            for cfg_file in extruders.glob("*.inst.cfg"):
                cfg = parse_cfg_file(cfg_file)
                if "metadata" in cfg:
                    sv = cfg["metadata"].get("setting_version")
                    if sv:
                        try:
                            return int(sv)
                        except ValueError:
                            continue
        
        return None
    
    def _discover_definitions(self) -> List[str]:
        """Discover available machine definition names."""
        definitions = []
        
        if not self.install_path:
            return definitions
        
        definitions_dir = self.install_path / "share" / "cura" / "resources" / "definitions"
        
        if definitions_dir.exists():
            for def_file in definitions_dir.glob("*.def.json"):
                name = def_file.stem
                # Skip abstract base definitions
                if name not in ("fdmprinter", "fdmextruder"):
                    definitions.append(name)
        
        return sorted(definitions)
    
    def validate_definition(self, definition_name: str) -> bool:
        """Check if a machine definition exists."""
        return definition_name in self.available_definitions or definition_name == "fdmprinter"
    
    def validate_settings(self, settings: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
        """
        Validate all settings in a dict.
        Returns (all_valid, errors, warnings).
        """
        errors = []
        warnings = []
        
        if not self.metadata or not self.metadata.loaded:
            return True, [], ["Validation skipped - metadata not loaded"]
        
        for key, value in settings.items():
            valid, msg = self.metadata.validate_value(key, value)
            if not valid:
                errors.append(f"{key}: {msg}")
            elif msg:
                warnings.append(f"{key}: {msg}")
        
        return len(errors) == 0, errors, warnings
    
    def generate_inst_cfg(
        self,
        profile_name: str,
        definition: str,
        quality_type: str,
        settings: Dict[str, Any],
        is_extruder: bool = False,
        extruder_position: int = 0
    ) -> str:
        """
        Generate the contents of a .inst.cfg file.
        """
        config = configparser.ConfigParser(interpolation=None)
        
        # [general] section
        config["general"] = {
            "version": "4",
            "name": profile_name,
            "definition": definition,
        }
        
        # [metadata] section
        config["metadata"] = {
            "type": "quality_changes",
            "quality_type": quality_type,
            "setting_version": str(self.setting_version or 23),
        }
        
        if is_extruder:
            config["metadata"]["position"] = str(extruder_position)
        
        # [values] section
        if settings:
            config["values"] = {}
            for key, value in settings.items():
                if self.metadata and self.metadata.loaded:
                    formatted = self.metadata.format_value_for_cfg(key, value)
                else:
                    formatted = str(value)
                config["values"][key] = formatted
        
        # Write to string
        output = io.StringIO()
        config.write(output)
        return output.getvalue()
    
    def build_curaprofile(
        self,
        profile_name: str,
        definition: str,
        quality_type: str,
        global_settings: Dict[str, Any],
        extruder_settings: Optional[Dict[int, Dict[str, Any]]] = None,
        output_path: Optional[Path] = None
    ) -> Tuple[bool, str, Optional[Path]]:
        """
        Build a complete .curaprofile ZIP file.
        
        Args:
            profile_name: Name of the profile (shown in Cura)
            definition: Machine definition name (e.g., 'creality_ender3pro')
            quality_type: Quality type (normal, draft, fine, etc.)
            global_settings: Settings that apply globally
            extruder_settings: Optional {extruder_index: settings_dict}
            output_path: Where to save (default: current directory)
        
        Returns:
            (success, message, output_path)
        """
        # Validate definition
        if self.available_definitions and not self.validate_definition(definition):
            available_sample = self.available_definitions[:10]
            return False, f"Unknown definition: {definition}. Examples: {available_sample}...", None
        
        # Validate settings
        valid, errors, warnings = self.validate_settings(global_settings)
        if not valid:
            return False, "Validation errors:\n" + "\n".join(errors), None
        
        if warnings:
            self.log("Validation warnings:")
            for w in warnings:
                self.log(f"  ⚠ {w}")
        
        # Separate global vs extruder settings
        global_only = {}
        extruder_only = {}
        
        for key, value in global_settings.items():
            if self.metadata and self.metadata.loaded and self.metadata.is_per_extruder(key):
                extruder_only[key] = value
            else:
                global_only[key] = value
        
        # Safe filename
        safe_name = re.sub(r'[^\w\-]', '_', profile_name)
        
        # Generate global config
        global_cfg = self.generate_inst_cfg(
            profile_name=profile_name,
            definition=definition,
            quality_type=quality_type,
            settings=global_only,
            is_extruder=False
        )
        
        # Generate extruder configs if needed
        extruder_cfgs = {}
        if extruder_only or extruder_settings:
            merged_extruder = {0: dict(extruder_only)}
            if extruder_settings:
                for pos, settings in extruder_settings.items():
                    if pos not in merged_extruder:
                        merged_extruder[pos] = {}
                    merged_extruder[pos].update(settings)
            
            for pos, settings in merged_extruder.items():
                if settings:
                    extruder_cfgs[pos] = self.generate_inst_cfg(
                        profile_name=profile_name,
                        definition=definition,
                        quality_type=quality_type,
                        settings=settings,
                        is_extruder=True,
                        extruder_position=pos
                    )
        
        # Determine output path
        if output_path is None:
            output_path = Path.cwd() / f"{safe_name}.curaprofile"
        else:
            output_path = Path(output_path)
            if output_path.is_dir():
                output_path = output_path / f"{safe_name}.curaprofile"
            elif not str(output_path).endswith('.curaprofile'):
                output_path = output_path.with_suffix('.curaprofile')
        
        # Create ZIP file
        try:
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(f"{safe_name}.inst.cfg", global_cfg)
                for pos, cfg_content in extruder_cfgs.items():
                    zf.writestr(f"{safe_name}_extruder_{pos}.inst.cfg", cfg_content)
            
            return True, f"Created: {output_path}", output_path
            
        except Exception as e:
            return False, f"Failed to create profile: {e}", None
    
    def build_from_preset(
        self,
        profile_name: str,
        definition: str,
        material_preset: str,
        quality_preset: str,
        custom_overrides: Optional[Dict[str, Any]] = None,
        output_path: Optional[Path] = None
    ) -> Tuple[bool, str, Optional[Path]]:
        """
        Build a profile from preset templates.
        """
        material_upper = material_preset.upper()
        quality_lower = quality_preset.lower()
        
        if material_upper not in MATERIAL_PRESETS:
            return False, f"Unknown material: {material_preset}. Available: {list(MATERIAL_PRESETS.keys())}", None
        
        if quality_lower not in QUALITY_PRESETS:
            return False, f"Unknown quality: {quality_preset}. Available: {list(QUALITY_PRESETS.keys())}", None
        
        # Merge presets (quality first, then material, then custom)
        settings = {}
        settings.update(QUALITY_PRESETS[quality_lower]["settings"])
        settings.update(MATERIAL_PRESETS[material_upper]["settings"])
        
        if custom_overrides:
            settings.update(custom_overrides)
        
        return self.build_curaprofile(
            profile_name=profile_name,
            definition=definition,
            quality_type=quality_lower,
            global_settings=settings,
            output_path=output_path
        )
    
    def build_from_json(
        self,
        json_path: Path,
        profile_name: str,
        definition: Optional[str] = None,
        quality_type: str = "normal",
        setting_filter: Optional[List[str]] = None,
        output_path: Optional[Path] = None
    ) -> Tuple[bool, str, Optional[Path]]:
        """
        Build a profile from a Cura Profile Extractor JSON file.
        """
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            return False, f"Failed to read JSON: {e}", None
        
        settings = {}
        
        # Try _key_settings first (curated important settings)
        if "_key_settings" in data:
            for key, info in data["_key_settings"].items():
                if isinstance(info, dict):
                    val = info.get("value")
                    if val is not None:
                        settings[key] = val
                else:
                    settings[key] = info
        
        # Then from machine effective_settings
        if "machine" in data and "effective_settings" in data["machine"]:
            for key, info in data["machine"]["effective_settings"].items():
                if key not in settings:
                    value = info.get("effective_value") or info.get("value") or info.get("default_value")
                    if value is not None:
                        settings[key] = value
        
        # Apply filter if provided
        if setting_filter:
            settings = {k: v for k, v in settings.items() if k in setting_filter}
        
        if not settings:
            return False, "No settings found in JSON file", None
        
        # Get definition from JSON if not provided
        if not definition:
            if "machine" in data:
                chain = data["machine"].get("inheritance_chain", [])
                if chain:
                    definition = chain[0].get("name", "fdmprinter")
                else:
                    definition = "fdmprinter"
            else:
                definition = "fdmprinter"
        
        self.log(f"  Loaded {len(settings)} settings from JSON")
        self.log(f"  Using definition: {definition}")
        
        return self.build_curaprofile(
            profile_name=profile_name,
            definition=definition,
            quality_type=quality_type,
            global_settings=settings,
            output_path=output_path
        )
    
    def list_presets(self) -> str:
        """Return formatted list of available presets."""
        lines = ["Available Presets:", ""]
        
        lines.append("Materials:")
        for name, info in MATERIAL_PRESETS.items():
            lines.append(f"  {name:6} - {info['description']}")
        
        lines.append("")
        lines.append("Quality:")
        for name, info in QUALITY_PRESETS.items():
            lines.append(f"  {name:6} - {info['description']}")
        
        return "\n".join(lines)


# =============================================================================
# CLI Interface
# =============================================================================

def run_cli(args):
    """Run profile building in CLI mode."""
    print(f"Cura Profile Builder v{__version__}")
    print("=" * 50)
    
    # List presets if requested
    if args.list_presets:
        builder = CuraBuilder(None, None)
        print(builder.list_presets())
        return 0
    
    # Auto-detect paths
    install_path = args.install or find_cura_install_path()
    appdata_path = args.appdata or find_cura_appdata_path()
    
    if not install_path:
        print("ERROR: Could not detect Cura install path.")
        print("  Use --install to specify, or set USER_INSTALL_PATH_OVERRIDE in script.")
        return 1
    
    print(f"Install: {install_path}")
    print(f"AppData: {appdata_path or '(not found - some features disabled)'}")
    
    # Initialize builder
    builder = CuraBuilder(str(install_path), str(appdata_path) if appdata_path else "")
    
    print("\nInitializing...")
    success, errors = builder.initialize()
    for err in errors:
        print(f"  Warning: {err}")
    
    # Determine build mode
    if args.from_json:
        # Build from extraction JSON
        print(f"\nBuilding from JSON: {args.from_json}")
        
        if not args.name:
            # Derive name from JSON filename
            args.name = Path(args.from_json).stem.replace("cura_profile_", "").replace("_", " ").title()
        
        success, message, output_path = builder.build_from_json(
            json_path=Path(args.from_json),
            profile_name=args.name,
            definition=args.definition,
            quality_type=args.quality_type or "normal",
            output_path=Path(args.output) if args.output else None
        )
        
    elif args.preset:
        # Build from preset
        if "/" not in args.preset:
            print("ERROR: Preset format should be 'MATERIAL/quality' (e.g., 'PLA/normal')")
            print("\n" + builder.list_presets())
            return 1
        
        material, quality = args.preset.split("/", 1)
        
        if not args.definition:
            print("ERROR: --definition required when using --preset")
            print("  Example: --definition creality_ender3pro")
            if builder.available_definitions:
                print(f"  Available: {builder.available_definitions[:15]}...")
            return 1
        
        if not args.name:
            args.name = f"{material.upper()} {quality.title()}"
        
        print(f"\nBuilding from preset: {material}/{quality}")
        print(f"  Profile name: {args.name}")
        print(f"  Definition: {args.definition}")
        
        success, message, output_path = builder.build_from_preset(
            profile_name=args.name,
            definition=args.definition,
            material_preset=material,
            quality_preset=quality,
            output_path=Path(args.output) if args.output else None
        )
        
    elif args.settings:
        # Build from command-line settings
        if not args.definition:
            print("ERROR: --definition required")
            return 1
        if not args.name:
            print("ERROR: --name required when using --settings")
            return 1
        
        # Parse settings (format: key=value,key=value)
        settings = {}
        for item in args.settings.split(","):
            if "=" in item:
                key, value = item.split("=", 1)
                # Try to parse as number/bool
                try:
                    if value.lower() in ("true", "false"):
                        value = value.lower() == "true"
                    elif "." in value:
                        value = float(value)
                    else:
                        value = int(value)
                except ValueError:
                    pass  # Keep as string
                settings[key.strip()] = value
        
        print(f"\nBuilding from settings: {len(settings)} values")
        success, message, output_path = builder.build_curaprofile(
            profile_name=args.name,
            definition=args.definition,
            quality_type=args.quality_type or "normal",
            global_settings=settings,
            output_path=Path(args.output) if args.output else None
        )
        
    else:
        print("\nERROR: Must specify one of:")
        print("  --preset MATERIAL/quality    (e.g., --preset PLA/normal)")
        print("  --from-json FILE.json        (from Cura Profile Extractor)")
        print("  --settings key=val,key=val   (manual settings)")
        print("\nRun with --list-presets to see available presets.")
        return 1
    
    # Report result
    if success:
        print(f"\n✓ {message}")
        print("\nTo import into Cura:")
        print("  1. Open Cura")
        print("  2. Go to Preferences → Profiles → Import")
        print(f"  3. Select: {output_path}")
        return 0
    else:
        print(f"\n✗ {message}")
        return 1


# =============================================================================
# GUI Interface (Phase 2 - Placeholder)
# =============================================================================

def run_gui():
    """Launch GUI mode."""
    if not TKINTER_AVAILABLE:
        print("ERROR: Tkinter not available. Use CLI mode instead.")
        print("  On Linux: sudo apt install python3-tk")
        print("  Run with --help for CLI options.")
        return 1
    
    # TODO: Phase 2 - Full GUI implementation
    print(f"Cura Profile Builder v{__version__}")
    print("\nGUI mode coming in Phase 2!")
    print("\nFor now, use CLI mode. Examples:")
    print("  python cura_profile_builder.py --preset PLA/normal --definition creality_ender3pro")
    print("  python cura_profile_builder.py --from-json my_extraction.json")
    print("  python cura_profile_builder.py --list-presets")
    print("\nRun with --help for all options.")
    return 0


# =============================================================================
# Entry Point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Cura Profile Builder - Create importable .curaprofile files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Build from preset (requires --definition)
  %(prog)s --preset PLA/normal --definition creality_ender3pro
  %(prog)s --preset PETG/fine --definition prusa_mk3s --name "My PETG Fine"
  
  # Build from extraction JSON (from Cura Profile Extractor)
  %(prog)s --from-json my_extraction.json
  %(prog)s --from-json extraction.json --name "Imported Profile" --definition creality_ender3pro
  
  # Build with manual settings
  %(prog)s --definition creality_ender3pro --name "Custom" --settings layer_height=0.2,infill_sparse_density=20
  
  # List available presets
  %(prog)s --list-presets

Presets: PLA, PETG, ABS, TPU, ASA × draft, normal, fine, ultra

Companion tool: Cura Profile Extractor
  https://github.com/ixhlbxi/Cura_Profile_Extractor
"""
    )
    
    # Build source (mutually exclusive)
    source = parser.add_argument_group("Build Source (choose one)")
    source.add_argument("--preset", type=str, 
                       help="Build from preset: MATERIAL/quality (e.g., PLA/normal)")
    source.add_argument("--from-json", type=str, 
                       help="Build from Cura Profile Extractor JSON file")
    source.add_argument("--settings", type=str,
                       help="Manual settings: key=value,key=value")
    
    # Required for some modes
    parser.add_argument("--definition", "-d", type=str,
                       help="Machine definition (e.g., creality_ender3pro)")
    parser.add_argument("--name", "-n", type=str,
                       help="Profile name (shown in Cura)")
    
    # Optional
    parser.add_argument("--quality-type", "-q", type=str, default="normal",
                       help="Quality type: draft, normal, fine, ultra (default: normal)")
    parser.add_argument("--output", "-o", type=str,
                       help="Output file path (default: profile_name.curaprofile)")
    
    # Path overrides
    parser.add_argument("--install", type=str,
                       help="Cura installation path (auto-detected)")
    parser.add_argument("--appdata", type=str,
                       help="Cura AppData path (auto-detected)")
    
    # Info
    parser.add_argument("--list-presets", action="store_true",
                       help="List available material and quality presets")
    parser.add_argument("--version", action="version", 
                       version=f"%(prog)s {__version__}")
    
    args = parser.parse_args()
    
    # If any build arguments provided, run CLI
    if args.preset or args.from_json or args.settings or args.list_presets:
        sys.exit(run_cli(args))
    else:
        # Default to GUI (or CLI help if no GUI)
        sys.exit(run_gui())


if __name__ == "__main__":
    main()
