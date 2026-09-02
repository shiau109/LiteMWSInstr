import os
import sys
import argparse
import shutil
import subprocess
import time
import numpy as np
import matplotlib
import tomlkit
from datetime import datetime
from typing import Any
from pathlib import Path

# Resolve local module paths before importing local packages.
# This ensures imports succeed regardless of the current working directory.
_script_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_script_dir)
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from resonator_tools import circuit

# Import refactored components
from orchestrator import ConfigManager, InstrumentDriver, ResonanceAnalyzer, ReportGenerator, TaskCompiler, BatchFitter, TLSAnalyzer
import builtins

# Headless matplotlib backend for automated scripts
matplotlib.use('Agg')

class TerminalLogger:
    def __init__(self, log_dir):
        os.makedirs(log_dir, exist_ok=True)
        self.log_file = open(os.path.join(log_dir, "vna_orchestrator.log"), "a", encoding="utf-8")
        self.original_print = builtins.print
        builtins.print = self.custom_print

    def custom_print(self, *args, **kwargs):
        sep = kwargs.get("sep", " ")
        end = kwargs.get("end", "\n")
        msg = sep.join(str(arg) for arg in args)
        
        # Always write everything to log file (convert \r to \n for clean log files)
        log_end = "\n" if end == "\r" else end
        self.log_file.write(msg + log_end)
        self.log_file.flush()
        
        # Filter console print
        msg_stripped = msg.lstrip()
        is_plot = "plot" in msg.lower() or "heatmap" in msg.lower() or "plots" in msg.lower()
        is_manual_prompt = "manual rescue" in msg.lower() or "manual range" in msg.lower()
        is_detailed = msg.startswith(" ") or msg.startswith("\t") or is_plot
        
        # Exceptions to always print on console (but never plot saving messages)
        is_exception = (
            not is_plot and (
                msg_stripped.startswith("C") or  # e.g., C61499 summary
                "successfully" in msg.lower() or
                "error" in msg.lower() or
                "warning" in msg.lower() or
                "failed" in msg.lower() or
                "completed" in msg.lower() or
                msg_stripped.startswith("=== ") or
                msg_stripped.startswith("--- ")
            )
        )
        
        if not is_detailed or is_exception or is_manual_prompt:
            if end == "\r":
                if sys.stdout.isatty():
                    self.original_print(f"\r{msg}\033[K", end="", flush=True)
                else:
                    self.original_print(msg)
            else:
                self.original_print(*args, **kwargs)

    def close(self):
        builtins.print = self.original_print
        self.log_file.close()

class VNAOrchestrator:
    def __init__(self, config_dir=None):
        # 1. Config Manager
        self.cfg = ConfigManager(config_dir)
        
        # Keep references to paths and configurations to maintain exact compatibility with main()
        self.config_dir = self.cfg.config_dir
        self.file_vna_config = self.cfg.file_vna_config
        self.file_res_pd = self.cfg.file_res_pd
        self.file_power_task = self.cfg.file_power_task
        
        self.vna_config = self.cfg.vna_config
        self.win_find_config = self.cfg.win_find_config
        self.res_pd_config = self.cfg.res_pd_config
        self.meas_lf_config = self.cfg.meas_lf_config
        
        # 2. Driver
        self.driver = InstrumentDriver(self.cfg)
        
        # 3. Analyzer
        self.analyzer = ResonanceAnalyzer(self.cfg)
        
        # 4. Reporter
        self.reporter = ReportGenerator(self.cfg)
        
        # 5. Compiler
        self.compiler = TaskCompiler(self.cfg)
        
        # 6. Fitter
        self.fitter = BatchFitter(self.cfg)
        
        # 7. TLS Analyzer
        self.tls_analyzer = TLSAnalyzer(self.cfg)
        
        # Temporary status trackers for reports
        self.current_v_start: float | None = None
        self.current_v_stop: float | None = None

    def _save_toml(self, config, path):
        """
        Saves TOML configuration (for backwards compatibility/main() CLI overrides).
        """
        self.cfg.save_toml(config, path)

    @staticmethod
    def _focus_file_in_vscode(file_path):
        """Open a file in the existing VS Code window and make its tab active."""
        code_cli = shutil.which("code.cmd") or shutil.which("code")
        if not code_cli:
            return False
        try:
            result = subprocess.run(
                ["cmd.exe", "/d", "/c", code_cli, "--reuse-window", os.path.abspath(file_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    @classmethod
    def _close_vscode_preview(cls, file_path):
        """Focus the preview again, then close only that active VS Code editor tab."""
        if os.name != "nt" or not cls._focus_file_in_vscode(file_path):
            return False
        try:
            import ctypes

            time.sleep(0.6)
            user32 = ctypes.windll.user32
            key_up = 0x0002
            user32.keybd_event(0x11, 0, 0, 0)       # Ctrl down
            user32.keybd_event(ord("W"), 0, 0, 0)   # W down
            user32.keybd_event(ord("W"), 0, key_up, 0)
            user32.keybd_event(0x11, 0, key_up, 0)  # Ctrl up
            return True
        except (AttributeError, OSError):
            return False

    @staticmethod
    def _estimate_manual_fwhm(freq_array, magnitude_db, minimum_idx):
        """Estimate dip FWHM from edge baseline and interpolated half-depth crossings."""
        freq_array = np.asarray(freq_array, dtype=float)
        magnitude_db = np.asarray(magnitude_db, dtype=float)
        edge_count = max(3, min(len(magnitude_db) // 10, 50))
        edge_values = np.concatenate((magnitude_db[:edge_count], magnitude_db[-edge_count:]))
        baseline_db = float(np.median(edge_values))
        minimum_db = float(magnitude_db[minimum_idx])
        half_level_db = minimum_db + 0.5 * (baseline_db - minimum_db)

        left_candidates = np.flatnonzero(magnitude_db[:minimum_idx] >= half_level_db)
        right_candidates = np.flatnonzero(magnitude_db[minimum_idx + 1:] >= half_level_db)
        if not len(left_candidates) or not len(right_candidates):
            return np.nan, half_level_db

        left_hi = int(left_candidates[-1])
        left_lo = left_hi + 1
        right_hi = int(minimum_idx + 1 + right_candidates[0])
        right_lo = right_hi - 1

        def interpolate_crossing(i0, i1):
            y0, y1 = magnitude_db[i0], magnitude_db[i1]
            if y1 == y0:
                return float(freq_array[i0])
            fraction = (half_level_db - y0) / (y1 - y0)
            return float(freq_array[i0] + fraction * (freq_array[i1] - freq_array[i0]))

        left_crossing = interpolate_crossing(left_hi, left_lo)
        right_crossing = interpolate_crossing(right_lo, right_hi)
        return max(0.0, right_crossing - left_crossing), half_level_db

    def find_all_windows(self, expected_dips_count=1):
        """
        Runs the window finding phase for all resonators defined in measurement_window_finding.toml.
        """
        print("\n" + "="*60)
        print("PHASE 1 & 2: FIND OPTIMIZED FREQUENCY SWEEP WINDOWS")
        print("="*60)
        
        self.driver.connect()
        vna_port = self.cfg.win_find_config["hardware"]["port"]
        measurements = self.cfg.win_find_config["measurement"]
        
        refined_resonators = []
        try:
            self.driver.setup_measurement(vna_port)
            for idx, task in enumerate(measurements):
                resonator_fre = task["frequency"]["resonator_fre"]
                deltafre = task["frequency"]["deltafre"]
                points = task["frequency"]["points"]
                power = task["power"]
                IF_bandwidth = task["IF_bandwidth"]
                
                print(f"\nResonator {idx + 1}/{len(measurements)} (Design Center: {resonator_fre/1e9:.5f} GHz):")
                final_start, final_stop = self.analyzer.run_optimized_peak_finding(
                    self.driver, resonator_fre, deltafre, points, power, IF_bandwidth,
                    expected_dips_count=expected_dips_count
                )
                
                refined_resonators.append({
                    "label": f"C{int(resonator_fre/1e5)}", # e.g. C46090
                    "start": final_start,
                    "stop": final_stop,
                    "design_freq": resonator_fre
                })
        finally:
            self.driver.disconnect()
            
        print("\nAll optimized sweep windows successfully located:")
        for r in refined_resonators:
            print(f"  {r['label']}: {r['start']/1e9:.6f} GHz to {r['stop']/1e9:.6f} GHz")
            
        # Dynamically update resonator_PD.toml
        self.cfg.update_resonator_pd_config(refined_resonators)

    def blind_search(self, start_freq, stop_freq, expected_count=None, prominence: float | str = 2.0,
                     manual_ranges=None, interactive_manual=False):
        """
        Task 1: Performs a blind search in [start_freq, stop_freq] to find all active resonators.
        Runs multi-pass sweeps with different power and noise levels, merges candidates,
        verifies ALL candidates first, and then filters based on expected count.
        Optional manual ranges are re-swept and their absolute minimum is force-added
        as a resonator, which provides a recovery path when automatic detection fails.
        """
        print("\n" + "="*60)
        print(f"BLIND RESONATOR SEARCH: {start_freq/1e9:.3f} to {stop_freq/1e9:.3f} GHz")
        print("="*60)
        
        # Load configurations from vna.toml
        verification_config = self.vna_config.get("verification", {})
        manual_ranges = list(manual_ranges or [])
        verification_span = float(verification_config.get("window_span_mhz", 10.0)) * 1e6
        verification_points = int(verification_config.get("points", 501))
        verification_power = verification_config.get("power", None)
        if verification_power is not None and str(verification_power).strip().lower() not in ["none", "auto", "null", ""]:
            try:
                verification_power = float(verification_power)
            except ValueError:
                verification_power = None
        else:
            verification_power = None
        verification_ibw = int(verification_config.get("if_bandwidth_hz", 200))
        verification_min_span = float(verification_config.get("min_span_mhz", 0.2)) * 1e6
        high_q_trigger_ratio = float(verification_config.get("high_q_trigger_ratio", 2.5))
        min_resweep_span = float(verification_config.get("min_resweep_span_mhz", 0.05)) * 1e6
        verification_prominence = verification_config.get("prominence_db", prominence)

        dedup_config = self.vna_config.get("deduplication", {})
        coarse_spacing = float(dedup_config.get("coarse_spacing_mhz", 0.25)) * 1e6
        precise_spacing = float(dedup_config.get("precise_spacing_mhz", 0.15)) * 1e6

        def parse_optional_float(val, default=None):
            if val is None:
                return default
            if isinstance(val, str) and val.strip().lower() in ["none", "null", "", "auto"]:
                return default
            try:
                return float(val)
            except ValueError:
                return default

        fwhm_config = self.vna_config.get("fwhm", {})
        min_fwhm_raw = parse_optional_float(fwhm_config.get("min_khz", 5.0))
        min_fwhm = min_fwhm_raw * 1e3 if min_fwhm_raw is not None else 5.0 * 1e3

        max_fwhm_raw = parse_optional_float(fwhm_config.get("max_mhz", 30.0))
        max_fwhm = max_fwhm_raw * 1e6 if max_fwhm_raw is not None else 30.0 * 1e6

        target_fwhm = float(fwhm_config.get("target_fwhm_khz", 300.0)) * 1e3
        sigma_dec = float(fwhm_config.get("fwhm_sigma_decade", 0.5))
        ns_mult = float(fwhm_config.get("noise_sigma_multiplier", 6.0))
        search_window_multiplier = float(fwhm_config.get("search_window_multiplier", fwhm_config.get("window_multiplier", 5.0)))
        fit_measurement_window_multiplier = float(fwhm_config.get("fit_measurement_window_multiplier", fwhm_config.get("window_multiplier", 15.0)))
        window_multiplier = fit_measurement_window_multiplier

        filtering_config = self.vna_config.get("filtering", {})
        scoring_method = str(filtering_config.get("scoring_method", "geometric")).strip().lower()

        min_arithmetic_score = parse_optional_float(filtering_config.get("min_arithmetic_score", None))
        min_geometric_score = parse_optional_float(filtering_config.get("min_geometric_score", None))
        max_chisq_fit = parse_optional_float(filtering_config.get("max_chisq_fit", None))
        max_fwhm_ratio = parse_optional_float(filtering_config.get("max_fwhm_ratio", None))
        min_fwhm_hard_khz = parse_optional_float(filtering_config.get("min_fwhm_khz", None))
        max_fwhm_hard_mhz = parse_optional_float(filtering_config.get("max_fwhm_mhz", None))
        weight_fwhm = float(filtering_config.get("weight_fwhm", 0.4))
        weight_depth = float(filtering_config.get("weight_depth", 0.3))
        weight_iq = float(filtering_config.get("weight_iq", 0.3))

        raw_allow_neg_qi = filtering_config.get("allow_negative_qi", True)
        if isinstance(raw_allow_neg_qi, str):
            allow_negative_qi = raw_allow_neg_qi.strip().lower() in ["true", "1", "yes"]
        else:
            allow_negative_qi = bool(raw_allow_neg_qi)

        min_fwhm_hard_hz = min_fwhm_hard_khz * 1e3 if min_fwhm_hard_khz is not None else None
        max_fwhm_hard_hz = max_fwhm_hard_mhz * 1e6 if max_fwhm_hard_mhz is not None else None

        passes_config = self.vna_config.get("blind_search_passes", {}).get("passes", [])
        sweep_passes = []
        for p in passes_config:
            sweep_passes.append({
                "power": float(p.get("power", -20.0)),
                "IF_bandwidth": int(p.get("if_bandwidth", p.get("IF_bandwidth", 1000))),
                "points": int(p.get("points", 16001)),
                "name": str(p.get("name", "Pass"))
            })
        if not sweep_passes:
            sweep_passes = [
                {"power": -15.0, "IF_bandwidth": 1000, "points": 16001, "name": "Pass 1 (High Power, -15 dBm)"},
                {"power": -35.0, "IF_bandwidth": 200, "points": 16001, "name": "Pass 2 (Low Power, -35 dBm)"},
                {"power": -45.0, "IF_bandwidth": 100, "points": 16001, "name": "Pass 3 (Ultra Low Power, -45 dBm)"}
            ]

        self.driver.connect()
        vna_port = self.cfg.vna_config["hardware"]["port"]
        
        # Reset dummy frequencies and clear existing resonators from config to force dynamic generation in the new swept range
        self.driver.dummy_resonator_fres = None
        if "resonator" in self.cfg.res_pd_config:
            self.cfg.res_pd_config["resonator"] = []
            self.cfg.save_toml(self.cfg.res_pd_config, self.cfg.file_res_pd)
            
        candidate_freqs = []
        cached_sweeps = []
        class ReportList(list[dict[str, Any]]):
            def __init__(self, orchestrator):
                super().__init__()
                self.orchestrator = orchestrator
            def append(self, item):
                if hasattr(self.orchestrator.analyzer, "last_noise_std"):
                    item["Est_Noise_Std_dB"] = self.orchestrator.analyzer.last_noise_std
                if hasattr(self.orchestrator.analyzer, "last_prominence_floor"):
                    item["Prominence_Floor_dB"] = self.orchestrator.analyzer.last_prominence_floor
                
                # Automatically inject actual measured Start and Stop bounds
                t = item.get("Type", "")
                if "Coarse" in t:
                    item["Start_Frequency_GHz"] = start_freq / 1e9
                    item["Stop_Frequency_GHz"] = stop_freq / 1e9
                elif hasattr(self.orchestrator, "current_v_start") and self.orchestrator.current_v_start is not None:
                    item["Start_Frequency_GHz"] = self.orchestrator.current_v_start
                    item["Stop_Frequency_GHz"] = self.orchestrator.current_v_stop
                    
                super().append(item)

        search_report = ReportList(self)
        
        try:
            self.driver.setup_measurement(vna_port)
                
            # Perform multi-pass sweeps
            for p_idx, p_config in enumerate(sweep_passes):
                p_name = p_config["name"]
                p_pow = p_config["power"]
                p_ibw = p_config["IF_bandwidth"]
                p_pts = p_config["points"]
                
                print(f"\n--- Running {p_name} ---")
                start_time_sweep = datetime.now()
                freq_array, s_params = self.driver.measure_sweep(
                    start_freq, stop_freq, p_pts, vna_port, p_pow, p_ibw
                )
                end_time_sweep = datetime.now()
                
                # Save coarse sweep raw data to NetCDF via ReportGenerator
                base_data_dir = self.cfg.res_pd_config.get("output", {}).get("data_path", "data/raw")
                nc_dir = os.path.join(base_data_dir, "nc")
                os.makedirs(nc_dir, exist_ok=True)
                coarse_file_path = os.path.join(
                    nc_dir, 
                    f"coarse_sweep_pass{p_idx+1}_{start_time_sweep.strftime('%Y%m%d_%H%M%S')}.nc"
                )
                attrs = {
                    "IF_bandwidth": int(p_ibw),
                    "power": float(p_pow),
                    "port": str(vna_port),
                    "start_time": str(start_time_sweep.strftime("%Y%m%d_%H%M%S")),
                    "end_time": str(end_time_sweep.strftime("%Y%m%d_%H%M%S")),
                    "points": int(p_pts),
                    "pass_name": str(p_name)
                }
                self.reporter.save_sweep_netcdf(coarse_file_path, freq_array, s_params, attrs, vna_port)
                
                # Cache results for visualization plot
                cached_sweeps.append((freq_array, s_params))
                
                # Find dips with high prominence
                discarded_coarse_dips = []
                dips = self.analyzer.find_dips(
                    freq_array, s_params, expected_count=expected_count, 
                    prominence=prominence, discarded_dips=discarded_coarse_dips
                )
                
                # Log coarse-sweep level filters and cuts
                for dip in discarded_coarse_dips:
                    search_report.append({
                        "Type": "Coarse Filtered",
                        "Coarse_Frequency_GHz": dip["freq"] / 1e9,
                        "Refined_Frequency_GHz": np.nan,
                        "Power_dBm": p_pow,
                        "IF_Bandwidth_Hz": p_ibw,
                        "Points": p_pts,
                        "FWHM_MHz": dip["fwhm"] / 1e6,
                        "Depth_dB": dip["mag"],
                        "Qi_fit": np.nan,
                        "ChiSq_fit": np.nan,
                        "Confidence_Score": dip.get("score", np.nan),
                        "Status": "Discarded",
                        "Reason": dip["reason"],
                        "Start_Frequency_GHz": np.nan,
                        "Stop_Frequency_GHz": np.nan
                    })
                
                print(f"{p_name} found {len(dips)} dip candidates (prominence >= {prominence} dB).")
                for dip in dips:
                    freq, mag, _, fwhm, initial_score, _, _ = dip
                    # Deduplicate: merge with existing candidates if within adaptive coarse_spacing
                    duplicate_idx = None
                    for c_idx, (f_c, m_c, fwhm_c, p_c, score_c) in enumerate(candidate_freqs):
                        spacing = max(coarse_spacing, 0.5 * fwhm, 0.5 * fwhm_c)
                        if abs(freq - f_c) < spacing:
                            duplicate_idx = c_idx
                            break
                            
                    if duplicate_idx is None:
                        print(f"  Candidate (New): {freq/1e9:.5f} GHz ({mag:.2f} dB, coarse FWHM: {fwhm/1e6:.3f} MHz, initial score: {initial_score:.1f}, power: {p_pow} dBm)")
                        candidate_freqs.append((freq, mag, fwhm, p_pow, initial_score))
                    else:
                        # Keep the one with the higher initial score
                        f_dup, m_dup, fwhm_dup, p_dup, score_dup = candidate_freqs[duplicate_idx]
                        if initial_score > score_dup:
                            print(f"  Candidate {freq/1e9:.5f} GHz (Score: {initial_score:.1f}) replaces duplicate (Score: {score_dup:.1f})")
                            search_report.append({
                                "Type": "Coarse Duplicate",
                                "Coarse_Frequency_GHz": f_dup / 1e9,
                                "Refined_Frequency_GHz": np.nan,
                                "Power_dBm": p_dup,
                                "IF_Bandwidth_Hz": p_ibw,
                                "Points": p_pts,
                                "FWHM_MHz": fwhm_dup / 1e6,
                                "Depth_dB": m_dup,
                                "Qi_fit": np.nan,
                                "ChiSq_fit": np.nan,
                                "Confidence_Score": score_dup,
                                "Status": "Discarded",
                                "Reason": f"Replaced by duplicate candidate at {freq/1e9:.5f} GHz with higher score ({initial_score:.1f} > {score_dup:.1f})",
                                "Start_Frequency_GHz": np.nan,
                                "Stop_Frequency_GHz": np.nan
                            })
                            candidate_freqs[duplicate_idx] = (freq, mag, fwhm, p_pow, initial_score)
                        else:
                            print(f"  Candidate {freq/1e9:.5f} GHz (Skipped, duplicate with higher or equal score already exists)")
                            search_report.append({
                                "Type": "Coarse Duplicate",
                                "Coarse_Frequency_GHz": freq / 1e9,
                                "Refined_Frequency_GHz": np.nan,
                                "Power_dBm": p_pow,
                                "IF_Bandwidth_Hz": p_ibw,
                                "Points": p_pts,
                                "FWHM_MHz": fwhm / 1e6,
                                "Depth_dB": mag,
                                "Qi_fit": np.nan,
                                "ChiSq_fit": np.nan,
                                "Confidence_Score": initial_score,
                                "Status": "Discarded",
                                "Reason": f"Duplicate of candidate at {f_dup/1e9:.5f} GHz (existing score {score_dup:.1f} >= {initial_score:.1f})",
                                "Start_Frequency_GHz": np.nan,
                                "Stop_Frequency_GHz": np.nan
                            })
            
            if not candidate_freqs:
                print("No candidate frequencies found in coarse sweeps.")

            print(f"\nTotal candidate frequencies before verification: {len(candidate_freqs)}")
            for idx, (f_c, m_c, fwhm_c, p_c, score_c) in enumerate(candidate_freqs):
                print(f"  {idx+1}: {f_c/1e9:.5f} GHz (found at {p_c} dBm, initial score: {score_c:.1f})")
                
            # Step B: Verification Sweep (Narrow High-Resolution sweeps around candidates)
            v_power = np.nan
            temp_refined_resonators = []
            all_verification_candidates = []
            for idx, (f_c, m_c, fwhm_c, p_c, score_c) in enumerate(candidate_freqs):
                print(f"\n--- Verifying Candidate {idx+1}/{len(candidate_freqs)} ({f_c/1e9:.5f} GHz) ---")
                                
                # Dynamic verification span: search_window_multiplier * coarse_FWHM, with a safe lower bound of 0.2 MHz
                span_v = max(verification_min_span, search_window_multiplier * fwhm_c)
                self.current_v_start = (f_c - span_v/2) / 1e9
                self.current_v_stop = (f_c + span_v/2) / 1e9
                
                print(f"  [Verification] Adaptive sweep span: {span_v/1e6:.3f} MHz (Range: {(f_c - span_v/2)/1e9:.6f} to {(f_c + span_v/2)/1e9:.6f} GHz)")
                
                v_power = verification_power if verification_power is not None else p_c
                print(f"  [Verification] Power used: {v_power} dBm")
                start_time_v = datetime.now()
                freq_array_v, s_params_v = self.driver.measure_sweep(
                    f_c - span_v/2, f_c + span_v/2, verification_points, vna_port, v_power, verification_ibw
                )
                end_time_v = datetime.now()
                
                # Save verification sweep raw data to NetCDF
                base_data_dir = self.cfg.res_pd_config.get("output", {}).get("data_path", "data/raw")
                nc_dir = os.path.join(base_data_dir, "nc")
                os.makedirs(nc_dir, exist_ok=True)
                fine_file_path = os.path.join(
                    nc_dir, 
                    f"verification_sweep_{idx+1}_coarse_{f_c/1e9:.5f}GHz_{start_time_v.strftime('%Y%m%d_%H%M%S')}.nc"
                )
                attrs_v = {
                    "IF_bandwidth": int(verification_ibw),
                    "power": float(v_power),
                    "port": str(vna_port),
                    "start_time": str(start_time_v.strftime("%Y%m%d_%H%M%S")),
                    "end_time": str(end_time_v.strftime("%Y%m%d_%H%M%S")),
                    "points": int(verification_points),
                    "coarse_freq_ghz": float(f_c / 1e9)
                }
                self.reporter.save_sweep_netcdf(fine_file_path, freq_array_v, s_params_v, attrs_v, vna_port)
                
                # Find all dips inside this narrow window
                discarded_verification_dips = []
                dips_v = self.analyzer.find_dips(
                    freq_array_v, s_params_v, expected_count=1, 
                    prominence=verification_prominence, discarded_dips=discarded_verification_dips
                )
                
                # Log verification FWHM filter discards
                for dip in discarded_verification_dips:
                    search_report.append({
                        "Type": "Verification Filtered",
                        "Coarse_Frequency_GHz": f_c / 1e9,
                        "Refined_Frequency_GHz": dip["freq"] / 1e9,
                        "Power_dBm": v_power,
                        "IF_Bandwidth_Hz": verification_ibw,
                        "Points": verification_points,
                        "FWHM_MHz": dip["fwhm"] / 1e6,
                        "Depth_dB": dip["mag"],
                        "Qi_fit": np.nan,
                        "ChiSq_fit": np.nan,
                        "Confidence_Score": dip.get("score", np.nan),
                        "Status": "Discarded",
                        "Reason": dip["reason"],
                        "Start_Frequency_GHz": np.nan,
                        "Stop_Frequency_GHz": np.nan
                    })
                
                if dips_v:
                    for dip_v in dips_v:
                        peak_freq, peak_mag, peak_idx, fwhm_v = dip_v[:4]
                        initial_score = dip_v[4]
                        s_fwhm_component = dip_v[5]
                        s_depth_component = dip_v[6]

                        print(f"  Dip verified at: {peak_freq/1e9:.6f} GHz ({peak_mag:.2f} dB)")
                        print(f"  Calculated FWHM: {fwhm_v/1e6:.3f} MHz")

                        # Option B: High-Q Narrow Dip Dynamic Resweep
                        # If actual verified FWHM is much narrower than initial verification span, perform high-resolution resweep
                        if fwhm_v > 0 and span_v > high_q_trigger_ratio * (search_window_multiplier * fwhm_v):
                            span_resweep = max(min_resweep_span, search_window_multiplier * fwhm_v)
                            print(f"  [Verification High-Q] Narrow dip detected (FWHM: {fwhm_v/1e3:.1f} kHz vs initial Span: {span_v/1e6:.2f} MHz).")
                            print(f"  [Verification High-Q] Performing dynamic high-resolution resweep across {span_resweep/1e6:.3f} MHz...")
                            freq_array_v, s_params_v = self.driver.measure_sweep(
                                peak_freq - span_resweep/2, peak_freq + span_resweep/2, verification_points, vna_port, v_power, verification_ibw
                            )
                            # Re-detect dip on high-resolution sweep
                            dips_resweep = self.analyzer.find_dips(
                                freq_array_v, s_params_v, expected_count=1,
                                prominence=verification_prominence, discarded_dips=[]
                            )
                            if dips_resweep:
                                dip_v = dips_resweep[0]
                                peak_freq, peak_mag, peak_idx, fwhm_v = dip_v[:4]
                                initial_score = dip_v[4]
                                s_fwhm_component = dip_v[5]
                                s_depth_component = dip_v[6]
                                print(f"  [Verification High-Q] Resweep verified at: {peak_freq/1e9:.6f} GHz ({peak_mag:.2f} dB), Refined FWHM: {fwhm_v/1e3:.1f} kHz")

                        # Hard Threshold Check 1: FWHM Hard Cutoffs (if configured)
                        if min_fwhm_hard_hz is not None and fwhm_v < min_fwhm_hard_hz:
                            reason_msg = f"FWHM ({fwhm_v/1e3:.1f} kHz) below hard threshold ({min_fwhm_hard_khz:.1f} kHz)"
                            print(f"  [Verification Filter] {reason_msg}. Discarding candidate.")
                            search_report.append({
                                "Type": "Verification Filtered",
                                "Coarse_Frequency_GHz": f_c / 1e9,
                                "Refined_Frequency_GHz": peak_freq / 1e9,
                                "Power_dBm": v_power,
                                "IF_Bandwidth_Hz": verification_ibw,
                                "Points": verification_points,
                                "FWHM_MHz": fwhm_v / 1e6,
                                "Depth_dB": peak_mag,
                                "Qi_fit": np.nan,
                                "ChiSq_fit": np.nan,
                                "Confidence_Score": np.nan,
                                "Status": "Discarded",
                                "Reason": reason_msg,
                                "Start_Frequency_GHz": np.nan,
                                "Stop_Frequency_GHz": np.nan
                            })
                            continue

                        if max_fwhm_hard_hz is not None and fwhm_v > max_fwhm_hard_hz:
                            reason_msg = f"FWHM ({fwhm_v/1e6:.2f} MHz) above hard threshold ({max_fwhm_hard_mhz:.1f} MHz)"
                            print(f"  [Verification Filter] {reason_msg}. Discarding candidate.")
                            search_report.append({
                                "Type": "Verification Filtered",
                                "Coarse_Frequency_GHz": f_c / 1e9,
                                "Refined_Frequency_GHz": peak_freq / 1e9,
                                "Power_dBm": v_power,
                                "IF_Bandwidth_Hz": verification_ibw,
                                "Points": verification_points,
                                "FWHM_MHz": fwhm_v / 1e6,
                                "Depth_dB": peak_mag,
                                "Qi_fit": np.nan,
                                "ChiSq_fit": np.nan,
                                "Confidence_Score": np.nan,
                                "Status": "Discarded",
                                "Reason": reason_msg,
                                "Start_Frequency_GHz": np.nan,
                                "Stop_Frequency_GHz": np.nan
                            })
                            continue

                        # Step B Trial Circle Fit Validation & Scoring
                        qi_val = np.nan
                        chi_val = np.nan
                        try:
                            # Use S-parameter port from configuration
                            port_str = self.cfg.vna_config.get("hardware", {}).get("port", "S21").upper()
                            if port_str in ["S11", "S22", "S33", "S44"]:
                                fit_port = circuit.reflection_port(f_data=freq_array_v, z_data_raw=s_params_v)
                            else:
                                fit_port = circuit.notch_port(f_data=freq_array_v, z_data_raw=s_params_v)
                            
                            fit_port.autofit()
                            
                            # Get fit parameters
                            if port_str in ["S11", "S22", "S33", "S44"]:
                                qi_val = fit_port.fitresults.get("Qi", np.nan)
                            else:
                                qi_val = fit_port.fitresults.get("Qi_dia_corr", np.nan)
                            chi_val = fit_port.fitresults.get("chi_square", np.nan)
                            
                            is_invalid_qi = np.isnan(qi_val) or (qi_val < 0 and not allow_negative_qi)
                            if is_invalid_qi or np.isnan(chi_val):
                                print(f"  [Verification Fit] Non-physical fit results (Qi={qi_val}, chi={chi_val}). Discarding candidate as false positive.")
                                search_report.append({
                                    "Type": "Fit Failure",
                                    "Coarse_Frequency_GHz": f_c / 1e9,
                                    "Refined_Frequency_GHz": peak_freq / 1e9,
                                    "Power_dBm": v_power,
                                    "IF_Bandwidth_Hz": verification_ibw,
                                    "Points": verification_points,
                                    "FWHM_MHz": fwhm_v / 1e6,
                                    "Depth_dB": peak_mag,
                                    "Qi_fit": qi_val,
                                    "ChiSq_fit": chi_val,
                                    "Confidence_Score": np.nan,
                                    "Status": "Discarded",
                                    "Reason": f"Non-physical fit results (Qi={qi_val}, chi_square={chi_val})",
                                    "Start_Frequency_GHz": np.nan,
                                    "Stop_Frequency_GHz": np.nan
                                })
                                continue

                            # Calculate Fitted FWHM (f0 / QL)
                            fr_fit_val = fit_port.fitresults.get("fr", np.nan)
                            ql_fit_val = fit_port.fitresults.get("Ql", np.nan)
                            if not np.isnan(fr_fit_val) and not np.isnan(ql_fit_val) and ql_fit_val > 0:
                                fwhm_fit_hz = fr_fit_val / ql_fit_val
                            else:
                                fwhm_fit_hz = np.nan

                            # Hard Threshold Check 2b & 2c: Fitted FWHM filtering & ratio check
                            is_deep_dip = (peak_mag < -30.0) or allow_negative_qi
                            if not np.isnan(fwhm_fit_hz):
                                is_failed_fwhm = False
                                reason_msg = ""
                                if min_fwhm_hard_hz is not None and fwhm_fit_hz < min_fwhm_hard_hz:
                                    is_failed_fwhm = True
                                    reason_msg = f"Fitted FWHM ({fwhm_fit_hz/1e3:.1f} kHz) below min_fwhm_khz threshold ({min_fwhm_hard_khz:.1f} kHz)"
                                elif max_fwhm_hard_hz is not None and fwhm_fit_hz > max_fwhm_hard_hz:
                                    is_failed_fwhm = True
                                    reason_msg = f"Fitted FWHM ({fwhm_fit_hz/1e6:.2f} MHz) exceeded max_fwhm_mhz threshold ({max_fwhm_hard_mhz:.1f} MHz)"
                                elif max_fwhm_ratio is not None and fwhm_v > 0 and fwhm_fit_hz > 0:
                                    ratio = max(fwhm_fit_hz / fwhm_v, fwhm_v / fwhm_fit_hz)
                                    if ratio > max_fwhm_ratio:
                                        is_failed_fwhm = True
                                        reason_msg = f"Fitted FWHM ({fwhm_fit_hz/1e6:.3f} MHz) and Spectrum FWHM ({fwhm_v/1e6:.3f} MHz) ratio ({ratio:.1f}x) exceeded max_fwhm_ratio threshold ({max_fwhm_ratio:.1f}x)"

                                if is_failed_fwhm:
                                    if is_deep_dip:
                                        print(f"  [Verification Fit] {reason_msg}, but deep dip / allow_negative_qi enabled. Falling back to spectrum FWHM ({fwhm_v/1e6:.3f} MHz).")
                                        fwhm_fit_hz = fwhm_v
                                    else:
                                        print(f"  [Verification Fit] {reason_msg}. Discarding candidate as false positive.")
                                        search_report.append({
                                            "Type": "Fit Failure",
                                            "Coarse_Frequency_GHz": f_c / 1e9,
                                            "Refined_Frequency_GHz": peak_freq / 1e9,
                                            "Power_dBm": v_power,
                                            "IF_Bandwidth_Hz": verification_ibw,
                                            "Points": verification_points,
                                            "FWHM_MHz": fwhm_v / 1e6,
                                            "FWHM_fit_MHz": fwhm_fit_hz / 1e6,
                                            "Depth_dB": peak_mag,
                                            "Qi_fit": qi_val,
                                            "ChiSq_fit": chi_val,
                                            "Confidence_Score": np.nan,
                                            "Status": "Discarded",
                                            "Reason": reason_msg,
                                            "Start_Frequency_GHz": np.nan,
                                            "Stop_Frequency_GHz": np.nan
                                        })
                                        continue

                            # Calculate circularity score S_IQ
                            chisq_norm = max_chisq_fit if max_chisq_fit is not None and max_chisq_fit > 0 else 0.05
                            s_iq = max(0.0, 100.0 * (1.0 - chi_val / chisq_norm))
                            
                            # Re-evaluate S_FWHM score component using Geometric Mean of Spectrum and Fitted FWHM
                            if not np.isnan(fwhm_fit_hz) and fwhm_fit_hz > 0 and fwhm_v > 0:
                                fwhm_eval = np.sqrt(fwhm_v * fwhm_fit_hz)
                            else:
                                fwhm_eval = fwhm_v
                            log10_eval = np.log10(fwhm_eval)
                            log10_target = np.log10(target_fwhm)
                            s_fwhm_component = 100.0 * np.exp(-((log10_eval - log10_target) ** 2) / (2.0 * (sigma_dec ** 2)))

                            # Arithmetic and Geometric scores
                            s_arithmetic = weight_fwhm * s_fwhm_component + weight_depth * s_depth_component + weight_iq * s_iq
                            
                            s_f_safe = max(0.01, s_fwhm_component)
                            s_d_safe = max(0.01, s_depth_component)
                            s_iq_safe = max(0.01, s_iq)
                            s_geometric = (s_f_safe ** weight_fwhm) * (s_d_safe ** weight_depth) * (s_iq_safe ** weight_iq)
                            
                            if scoring_method == "arithmetic":
                                final_score = s_arithmetic
                            else:
                                final_score = s_geometric

                            cand_info = {
                                "label": f"C{int(peak_freq/1e5)}",
                                "start": peak_freq - window_multiplier * fwhm_v,
                                "stop": peak_freq + window_multiplier * fwhm_v,
                                "design_freq": peak_freq,
                                "verified_depth": peak_mag,
                                "fwhm": fwhm_v,
                                "fwhm_fit": fwhm_fit_hz,
                                "freq_v": freq_array_v,
                                "s21_v": s_params_v,
                                "s21_sim": fit_port.z_data_sim if hasattr(fit_port, "z_data_sim") else None,
                                "z_data_raw": fit_port.z_data_raw if hasattr(fit_port, "z_data_raw") else None,
                                "confidence_score": final_score,
                                "qi_fit": qi_val,
                                "chisq_fit": chi_val,
                                "coarse_freq": f_c,
                                "v_power": v_power,
                                "v_ibw": verification_ibw,
                                "v_pts": verification_points,
                                "status": "Discarded"
                            }
                            all_verification_candidates.append(cand_info)

                            # Hard Threshold Check 3: Score Threshold for Selected Method (if configured)
                            if scoring_method == "arithmetic":
                                if min_arithmetic_score is not None and s_arithmetic < min_arithmetic_score:
                                    reason_msg = f"Arithmetic score ({s_arithmetic:.1f}) below threshold ({min_arithmetic_score:.1f})"
                                    print(f"  [Verification Score Filter] {reason_msg}. Discarding candidate.")
                                    search_report.append({
                                        "Type": "Score Filtered",
                                        "Coarse_Frequency_GHz": f_c / 1e9,
                                        "Refined_Frequency_GHz": peak_freq / 1e9,
                                        "Power_dBm": v_power,
                                        "IF_Bandwidth_Hz": verification_ibw,
                                        "Points": verification_points,
                                        "FWHM_MHz": fwhm_v / 1e6,
                                        "FWHM_fit_MHz": fwhm_fit_hz / 1e6,
                                        "Depth_dB": peak_mag,
                                        "Qi_fit": qi_val,
                                        "ChiSq_fit": chi_val,
                                        "Confidence_Score": final_score,
                                        "Status": "Discarded",
                                        "Reason": reason_msg,
                                        "Start_Frequency_GHz": np.nan,
                                        "Stop_Frequency_GHz": np.nan
                                    })
                                    continue
                            else:
                                if min_geometric_score is not None and s_geometric < min_geometric_score:
                                    reason_msg = f"Geometric score ({s_geometric:.1f}) below threshold ({min_geometric_score:.1f})"
                                    print(f"  [Verification Score Filter] {reason_msg}. Discarding candidate.")
                                    search_report.append({
                                        "Type": "Score Filtered",
                                        "Coarse_Frequency_GHz": f_c / 1e9,
                                        "Refined_Frequency_GHz": peak_freq / 1e9,
                                        "Power_dBm": v_power,
                                        "IF_Bandwidth_Hz": verification_ibw,
                                        "Points": verification_points,
                                        "FWHM_MHz": fwhm_v / 1e6,
                                        "FWHM_fit_MHz": fwhm_fit_hz / 1e6,
                                        "Depth_dB": peak_mag,
                                        "Qi_fit": qi_val,
                                        "ChiSq_fit": chi_val,
                                        "Confidence_Score": final_score,
                                        "Status": "Discarded",
                                        "Reason": reason_msg,
                                        "Start_Frequency_GHz": np.nan,
                                        "Stop_Frequency_GHz": np.nan
                                    })
                                    continue

                            print(f"  [Verification Fit] Fit succeeded ({scoring_method}): Qi={qi_val:.1f}, chi_square={chi_val:.5f}, Score={final_score:.1f} (Arith={s_arithmetic:.1f}, Geom={s_geometric:.1f})")
                            
                        except Exception as fit_err:
                            # In case fitting fails completely
                            print(f"  [Verification Fit] Trial fit failed: {fit_err}. Discarding candidate as false positive.")
                            search_report.append({
                                "Type": "Fit Failure",
                                "Coarse_Frequency_GHz": f_c / 1e9,
                                "Refined_Frequency_GHz": peak_freq / 1e9,
                                "Power_dBm": v_power,
                                "IF_Bandwidth_Hz": verification_ibw,
                                "Points": verification_points,
                                "FWHM_MHz": fwhm_v / 1e6,
                                "Depth_dB": peak_mag,
                                "Qi_fit": np.nan,
                                "ChiSq_fit": np.nan,
                                "Confidence_Score": np.nan,
                                "Status": "Discarded",
                                "Reason": f"Trial fit failed: {fit_err}",
                                "Start_Frequency_GHz": np.nan,
                                "Stop_Frequency_GHz": np.nan
                            })
                            continue

                        # Apply adaptive guardrails
                        max_fwhm_adaptive = max(max_fwhm, 2.0 * fwhm_c)
                        if fwhm_v < min_fwhm: fwhm_v = min_fwhm
                        if fwhm_v > max_fwhm_adaptive: fwhm_v = max_fwhm_adaptive
                        
                        # Final window is exactly the configured multiple of FWHM.
                        half_window_span = window_multiplier * fwhm_v
                        final_start = peak_freq - half_window_span
                        final_stop = peak_freq + half_window_span
                        cand_info["start"] = final_start
                        cand_info["stop"] = final_stop
                        cand_info["fwhm"] = fwhm_v

                        # The verification trace is often narrower than the final
                        # ±N×FWHM window. Measure the complete final window so the
                        # review plot contains only real raw data with no padding.
                        if freq_array_v.min() > final_start or freq_array_v.max() < final_stop:
                            print(
                                f"  [Window Preview] Measuring full {window_multiplier:g}×FWHM "
                                "window for raw-data review..."
                            )
                            preview_start_time = datetime.now()
                            freq_window, s_params_window = self.driver.measure_sweep(
                                final_start, final_stop, verification_points,
                                vna_port, v_power, verification_ibw
                            )
                            cand_info["freq_v"] = freq_window
                            cand_info["s21_v"] = s_params_window
                            cand_info["z_data_raw"] = s_params_window
                            cand_info["s21_sim"] = None
                            preview_path = os.path.join(
                                base_data_dir, "nc",
                                f"window_preview_{cand_info['label']}_"
                                f"{preview_start_time.strftime('%Y%m%d_%H%M%S')}.nc"
                            )
                            self.reporter.save_sweep_netcdf(preview_path, freq_window, s_params_window, {
                                "IF_bandwidth": int(verification_ibw),
                                "power": float(v_power),
                                "port": str(vna_port),
                                "points": int(verification_points),
                                "window_multiplier": float(window_multiplier),
                                "fwhm_hz": float(fwhm_v),
                                "window_start_ghz": float(final_start / 1e9),
                                "window_stop_ghz": float(final_stop / 1e9),
                                "measurement_purpose": "raw_final_window_preview",
                            }, vna_port)
                        
                        temp_refined_resonators.append(cand_info)
                else:
                    print(f"  Warning: No dip verified around {f_c/1e9:.5f} GHz. Discarding candidate as false positive.")
                    search_report.append({
                        "Type": "Verification Failure",
                        "Coarse_Frequency_GHz": f_c / 1e9,
                        "Refined_Frequency_GHz": np.nan,
                        "Power_dBm": v_power,
                        "IF_Bandwidth_Hz": verification_ibw,
                        "Points": verification_points,
                        "FWHM_MHz": np.nan,
                        "Depth_dB": np.nan,
                        "Qi_fit": np.nan,
                        "ChiSq_fit": np.nan,
                        "Confidence_Score": np.nan,
                        "Status": "Discarded",
                        "Reason": "No dip verified in verification sweep",
                        "Start_Frequency_GHz": np.nan,
                        "Stop_Frequency_GHz": np.nan
                    })
            
            # Ask for manual rescue windows only after every automatic verification
            # sweep has finished, so the preview marks candidates that actually
            # survived fine-scan filtering.
            if interactive_manual:
                base_data_dir = self.cfg.res_pd_config.get("output", {}).get("data_path", "data/raw")
                selection_plot = self.reporter.save_manual_selection_preview(
                    base_data_dir, cached_sweeps, sweep_passes, vna_port,
                    detected_frequencies=[r["design_freq"] for r in temp_refined_resonators]
                )
                print("\nManual rescue (after verification): enter frequency windows in GHz.")
                preview_opened = False
                if selection_plot:
                    preview_opened = self._focus_file_in_vscode(selection_plot)
                    if preview_opened:
                        print(f"Manual rescue selection plot opened in VS Code:\n  {selection_plot}")
                    else:
                        print("Warning: Could not open the manual selection plot in VS Code automatically.")
                        print(f"Manual rescue selection file:\n  {selection_plot}")
                print("Green lines are resonators retained after fine-scan verification.")
                print("Format: start:stop (for example 4.48:4.52). Enter a blank line when finished.")
                try:
                    while True:
                        try:
                            raw_range = input("Manual range [GHz]: ").strip()
                        except EOFError:
                            raw_range = ""
                        if not raw_range:
                            break
                        try:
                            left, right = raw_range.replace(",", ":").split(":", 1)
                            range_start, range_stop = sorted((float(left), float(right)))
                            if range_start == range_stop:
                                raise ValueError("start and stop must differ")
                            manual_ranges.append((range_start * 1e9, range_stop * 1e9))
                            print(f"  Added manual window: {range_start:.6f} to {range_stop:.6f} GHz")
                        except ValueError as exc:
                            print(f"  Invalid range '{raw_range}': {exc}")
                finally:
                    if preview_opened and selection_plot:
                        if self._close_vscode_preview(selection_plot):
                            print("Manual rescue selection plot closed in VS Code.")
                        else:
                            print("Warning: Could not close the VS Code selection plot automatically.")

            # Manual rescue: re-sweep each user-selected range and force the lowest
            # magnitude point into the final resonator list. This intentionally bypasses
            # the automatic prominence/FWHM/fit filters.
            manual_cfg = self.vna_config.get("manual_rescue", {})
            manual_points = int(manual_cfg.get("points", max(verification_points, 1001)))
            manual_ibw = int(manual_cfg.get("if_bandwidth_hz", verification_ibw))
            # Manual rescues use the same final-window rule as automatically
            # verified resonators, instead of maintaining a separate multiplier.
            manual_window_multiplier = window_multiplier
            manual_power_cfg = manual_cfg.get("power", verification_power)
            if manual_power_cfg is None or str(manual_power_cfg).strip().lower() in ["auto", "none", "null", ""]:
                manual_power = float(sweep_passes[-1]["power"])
            else:
                manual_power = float(manual_power_cfg)

            for manual_idx, (range_start, range_stop) in enumerate(manual_ranges, start=1):
                range_start, range_stop = sorted((float(range_start), float(range_stop)))
                clipped_start = max(start_freq, range_start)
                clipped_stop = min(stop_freq, range_stop)
                if clipped_start >= clipped_stop:
                    print(f"Warning: Manual range {range_start/1e9:.6f}:{range_stop/1e9:.6f} GHz is outside the blind-search span; skipped.")
                    continue

                print(f"\n--- Manual Rescue {manual_idx}/{len(manual_ranges)} ({clipped_start/1e9:.6f} to {clipped_stop/1e9:.6f} GHz) ---")
                start_time_manual = datetime.now()
                freq_manual, s_params_manual = self.driver.measure_sweep(
                    clipped_start, clipped_stop, manual_points, vna_port, manual_power, manual_ibw
                )
                mag_manual = 20 * np.log10(np.maximum(np.abs(s_params_manual), 1e-18))
                minimum_idx = int(np.argmin(mag_manual))
                minimum_freq = float(freq_manual[minimum_idx])
                minimum_mag = float(mag_manual[minimum_idx])
                label = f"C{int(minimum_freq/1e5)}"
                measured_fwhm, half_level_db = self._estimate_manual_fwhm(
                    freq_manual, mag_manual, minimum_idx
                )
                if not np.isfinite(measured_fwhm) or measured_fwhm <= 0:
                    measured_fwhm = max(
                        (clipped_stop - clipped_start) / max(2.0 * manual_window_multiplier, 1.0),
                        min_fwhm
                    )
                    fwhm_method = "fallback_from_selection_span"
                    print(f"  Warning: FWHM crossings not contained in the selected range; using {measured_fwhm/1e6:.3f} MHz fallback.")
                else:
                    measured_fwhm = max(measured_fwhm, min_fwhm)
                    fwhm_method = "half_depth_crossings"

                manual_half_window = manual_window_multiplier * measured_fwhm
                manual_window_start = max(start_freq, minimum_freq - manual_half_window)
                manual_window_stop = min(stop_freq, minimum_freq + manual_half_window)

                base_data_dir = self.cfg.res_pd_config.get("output", {}).get("data_path", "data/raw")
                manual_file_path = os.path.join(
                    base_data_dir, "nc",
                    f"manual_rescue_{manual_idx}_{minimum_freq/1e9:.6f}GHz_{start_time_manual.strftime('%Y%m%d_%H%M%S')}.nc"
                )
                self.reporter.save_sweep_netcdf(manual_file_path, freq_manual, s_params_manual, {
                    "IF_bandwidth": manual_ibw,
                    "power": manual_power,
                    "port": str(vna_port),
                    "points": manual_points,
                    "selection_start_ghz": clipped_start / 1e9,
                    "selection_stop_ghz": clipped_stop / 1e9,
                    "selection_method": "manual_window_minimum",
                    "fwhm_hz": measured_fwhm,
                    "fwhm_method": fwhm_method,
                    "half_depth_level_db": half_level_db,
                    "final_window_start_ghz": manual_window_start / 1e9,
                    "final_window_stop_ghz": manual_window_stop / 1e9
                }, vna_port)

                # Keep the original recovery scan, then acquire the complete
                # ±N×FWHM final window if the selected scan did not cover it.
                freq_manual_preview = freq_manual
                s_params_manual_preview = s_params_manual
                if freq_manual.min() > manual_window_start or freq_manual.max() < manual_window_stop:
                    print(
                        f"  [Window Preview] Measuring full {manual_window_multiplier:g}×FWHM "
                        "manual window for raw-data review..."
                    )
                    preview_start_time = datetime.now()
                    freq_manual_preview, s_params_manual_preview = self.driver.measure_sweep(
                        manual_window_start, manual_window_stop, manual_points,
                        vna_port, manual_power, manual_ibw
                    )
                    manual_preview_path = os.path.join(
                        base_data_dir, "nc",
                        f"window_preview_{label}_{preview_start_time.strftime('%Y%m%d_%H%M%S')}.nc"
                    )
                    self.reporter.save_sweep_netcdf(
                        manual_preview_path, freq_manual_preview, s_params_manual_preview, {
                            "IF_bandwidth": manual_ibw,
                            "power": manual_power,
                            "port": str(vna_port),
                            "points": manual_points,
                            "window_multiplier": float(manual_window_multiplier),
                            "fwhm_hz": float(measured_fwhm),
                            "window_start_ghz": float(manual_window_start / 1e9),
                            "window_stop_ghz": float(manual_window_stop / 1e9),
                            "measurement_purpose": "raw_final_window_preview",
                        }, vna_port
                    )

                cand_info = {
                    "label": label,
                    "start": manual_window_start,
                    "stop": manual_window_stop,
                    "design_freq": minimum_freq,
                    "verified_depth": minimum_mag,
                    "fwhm": measured_fwhm,
                    "fwhm_fit": np.nan,
                    "freq_v": freq_manual_preview,
                    "s21_v": s_params_manual_preview,
                    "s21_sim": None,
                    "z_data_raw": s_params_manual_preview,
                    "confidence_score": 10000.0,
                    "qi_fit": np.nan,
                    "chisq_fit": np.nan,
                    "coarse_freq": minimum_freq,
                    "v_power": manual_power,
                    "v_ibw": manual_ibw,
                    "v_pts": manual_points,
                    "status": "Passed",
                    "source": "manual_window_minimum"
                }
                temp_refined_resonators.append(cand_info)
                all_verification_candidates.append(cand_info)
                print(f"  Resonator {label}: minimum at {minimum_freq/1e9:.9f} GHz ({minimum_mag:.2f} dB), FWHM {measured_fwhm/1e6:.3f} MHz")
                print(f"  Adaptive window (±{manual_window_multiplier:g} x FWHM): {manual_window_start/1e9:.9f} to {manual_window_stop/1e9:.9f} GHz")
                search_report.append({
                    "Type": "Manual Rescue",
                    "Coarse_Frequency_GHz": minimum_freq / 1e9,
                    "Refined_Frequency_GHz": minimum_freq / 1e9,
                    "Power_dBm": manual_power,
                    "IF_Bandwidth_Hz": manual_ibw,
                    "Points": manual_points,
                    "FWHM_MHz": measured_fwhm / 1e6,
                    "FWHM_fit_MHz": np.nan,
                    "Depth_dB": minimum_mag,
                    "Qi_fit": np.nan,
                    "ChiSq_fit": np.nan,
                    "Confidence_Score": 10000.0,
                    "Status": "Passed",
                    "Reason": "User-selected window; absolute minimum force-added",
                    "Next_Sweep_Start_GHz": manual_window_start / 1e9,
                    "Next_Sweep_Stop_GHz": manual_window_stop / 1e9
                })

            # Deduplicate verified resonators based on precise design_freq using adaptive spacing
            unique_refined = []
            for r in temp_refined_resonators:
                duplicate = False
                for ur_idx, ur in enumerate(unique_refined):
                    spacing = max(precise_spacing, 0.5 * r["fwhm"], 0.5 * ur["fwhm"])
                    if abs(r["design_freq"] - ur["design_freq"]) < spacing:
                        duplicate = True
                        # Keep the one with the higher confidence score
                        if r["confidence_score"] > ur["confidence_score"]:
                            search_report.append({
                                "Type": "Precise Duplicate",
                                "Coarse_Frequency_GHz": ur["coarse_freq"] / 1e9 if "coarse_freq" in ur else np.nan,
                                "Refined_Frequency_GHz": ur["design_freq"] / 1e9,
                                "Power_dBm": v_power,
                                "IF_Bandwidth_Hz": verification_ibw,
                                "Points": verification_points,
                                "FWHM_MHz": ur["fwhm"] / 1e6,
                                "Depth_dB": ur["verified_depth"],
                                "Qi_fit": ur.get("qi_fit", np.nan),
                                "ChiSq_fit": ur.get("chisq_fit", np.nan),
                                "Confidence_Score": ur["confidence_score"],
                                "Status": "Discarded",
                                "Reason": f"Deduplicated (replaced by close candidate at {r['design_freq']/1e9:.5f} GHz with higher score {r['confidence_score']:.1f} > {ur['confidence_score']:.1f})",
                                "Start_Frequency_GHz": np.nan,
                                "Stop_Frequency_GHz": np.nan
                            })
                            unique_refined[ur_idx] = r
                        else:
                            search_report.append({
                                "Type": "Precise Duplicate",
                                "Coarse_Frequency_GHz": r["coarse_freq"] / 1e9 if "coarse_freq" in r else np.nan,
                                "Refined_Frequency_GHz": r["design_freq"] / 1e9,
                                "Power_dBm": v_power,
                                "IF_Bandwidth_Hz": verification_ibw,
                                "Points": verification_points,
                                "FWHM_MHz": r["fwhm"] / 1e6,
                                "Depth_dB": r["verified_depth"],
                                "Qi_fit": r.get("qi_fit", np.nan),
                                "ChiSq_fit": r.get("chisq_fit", np.nan),
                                "Confidence_Score": r["confidence_score"],
                                "Status": "Discarded",
                                "Reason": f"Deduplicated (candidate at {ur['design_freq']/1e9:.5f} GHz with higher score {ur['confidence_score']:.1f} >= {r['confidence_score']:.1f} already exists)",
                                "Start_Frequency_GHz": np.nan,
                                "Stop_Frequency_GHz": np.nan
                            })
                        break
                if not duplicate:
                    unique_refined.append(r)
            temp_refined_resonators = unique_refined
            
            # --- Post-Filtering (Filter-Last) ---
            refined_resonators = []
            if expected_count is not None:
                # Sort verified resonators by confidence score (highest score first)
                sorted_resonators = sorted(temp_refined_resonators, key=lambda x: x["confidence_score"], reverse=True)
                if len(sorted_resonators) > expected_count:
                    print(f"\nFiltering: Found {len(sorted_resonators)} verified resonators but expected {expected_count}. Selecting the ones with the highest confidence score.")
                    refined_resonators = sorted_resonators[:expected_count]
                    for r in sorted_resonators[expected_count:]:
                        search_report.append({
                            "Type": "Post-Filtering",
                            "Coarse_Frequency_GHz": r["coarse_freq"] / 1e9 if "coarse_freq" in r else np.nan,
                            "Refined_Frequency_GHz": r["design_freq"] / 1e9,
                            "Power_dBm": v_power,
                            "IF_Bandwidth_Hz": verification_ibw,
                            "Points": verification_points,
                            "FWHM_MHz": r["fwhm"] / 1e6,
                            "Depth_dB": r["verified_depth"],
                            "Qi_fit": r.get("qi_fit", np.nan),
                            "ChiSq_fit": r.get("chisq_fit", np.nan),
                            "Confidence_Score": r["confidence_score"],
                            "Status": "Discarded",
                            "Reason": f"Post-filtered (score ranked below top {expected_count} expected limit)",
                            "Start_Frequency_GHz": np.nan,
                            "Stop_Frequency_GHz": np.nan
                        })
                else:
                    refined_resonators = sorted_resonators
                    if len(refined_resonators) < expected_count:
                        print(f"\nWarning: Expected {expected_count} resonators, but only {len(refined_resonators)} verified successfully.")
            else:
                # Keep all verified resonators
                print(f"\nDynamic Mode: Keeping all {len(temp_refined_resonators)} successfully verified resonators.")
                refined_resonators = temp_refined_resonators
                
            # Re-sort chronologically by frequency order
            refined_resonators = sorted(refined_resonators, key=lambda x: x["design_freq"])
            
            for r in refined_resonators:
                r["status"] = "Passed"
                # Update current_v_start and current_v_stop to reflect actual verification sweep bounds
                if "freq_v" in r:
                    self.current_v_start = float(r["freq_v"].min() / 1e9)
                    self.current_v_stop = float(r["freq_v"].max() / 1e9)
                search_report.append({
                    "Type": "Resonator",
                    "Coarse_Frequency_GHz": r["coarse_freq"] / 1e9 if "coarse_freq" in r else np.nan,
                    "Refined_Frequency_GHz": r["design_freq"] / 1e9,
                    "Power_dBm": r.get("v_power", np.nan),
                    "IF_Bandwidth_Hz": r.get("v_ibw", np.nan),
                    "Points": r.get("v_pts", np.nan),
                    "FWHM_MHz": r["fwhm"] / 1e6,
                    "FWHM_fit_MHz": r.get("fwhm_fit", np.nan) / 1e6 if not np.isnan(r.get("fwhm_fit", np.nan)) else np.nan,
                    "Depth_dB": r["verified_depth"],
                    "Qi_fit": r.get("qi_fit", np.nan),
                    "ChiSq_fit": r.get("chisq_fit", np.nan),
                    "Confidence_Score": r["confidence_score"],
                    "Status": "Passed",
                    "Reason": "N/A",
                    "Next_Sweep_Start_GHz": r["start"] / 1e9,
                    "Next_Sweep_Stop_GHz": r["stop"] / 1e9
                })
                
        finally:
            self.driver.disconnect()
            
        # Update resonator_PD.toml
        self.cfg.update_resonator_pd_config(refined_resonators)
  
        # Generate CSV Audit Report via ReportGenerator
        filtering_cfg = self.vna_config.get("filtering", {})
        configs_dict = {
            "min_fwhm": min_fwhm,
            "max_fwhm": max_fwhm,
            "target_fwhm": target_fwhm,
            "sigma_dec": sigma_dec,
            "ns_mult": ns_mult,
            "window_multiplier": window_multiplier,
            "coarse_spacing": coarse_spacing,
            "precise_spacing": precise_spacing,
            "verification_span": verification_span,
            "verification_points": verification_points,
            "verification_ibw": verification_ibw,
            "scoring_method": filtering_cfg.get("scoring_method", "geometric"),
            "min_arithmetic_score": filtering_cfg.get("min_arithmetic_score", "N/A"),
            "min_geometric_score": filtering_cfg.get("min_geometric_score", "N/A"),
            "max_chisq_fit": filtering_cfg.get("max_chisq_fit", "N/A"),
            "max_fwhm_ratio": filtering_cfg.get("max_fwhm_ratio", "N/A"),
            "min_fwhm_khz": filtering_cfg.get("min_fwhm_khz", "N/A"),
            "max_fwhm_mhz": filtering_cfg.get("max_fwhm_mhz", "N/A")
        }
        base_data_dir = self.cfg.res_pd_config.get("output", {}).get("data_path", "data/raw")
        self.reporter.generate_audit_csv(base_data_dir, start_freq, stop_freq, search_report, configs_dict)

        print("\n=== Blind Search Completed ===")
        print(f"Successfully verified and windowed {len(refined_resonators)} resonators:")
        for r in refined_resonators:
            print(f"  {r['label']}: {r['start']/1e9:.6f} GHz to {r['stop']/1e9:.6f} GHz (verified depth: {r['verified_depth']:.2f} dB, confidence score: {r['confidence_score']:.1f})")
            
        # Generate plots
        self.reporter.generate_plots(base_data_dir, all_verification_candidates, refined_resonators, cached_sweeps, sweep_passes, vna_port)
        self._window_review_context = {
            "refined_resonators": refined_resonators,
            "cached_sweeps": cached_sweeps,
            "vna_port": vna_port,
        }

    def compile_power_tasks(self):
        """
        Delegates Phase 3 power task compiling to the TaskCompiler.
        """
        self.compiler.compile_power_tasks()
        # Synchronize back res_pd_config from cfg in case caller needs to inspect it
        self.res_pd_config = self.cfg.res_pd_config

    def review_run_all_windows(self):
        """Show final windows and allow interactive overrides before task compilation."""
        resonators = self.cfg.res_pd_config.get("resonator", [])
        if not resonators:
            print("Warning: No resonator windows are available for run-all review.")
            return

        base_data_dir = self.cfg.res_pd_config.get("output", {}).get("data_path", "data/raw")
        window_plot = os.path.abspath(os.path.join(
            base_data_dir, "plots", "blind_search_resonator_windows.png"
        ))
        preview_opened = False
        if os.path.exists(window_plot):
            preview_opened = self._focus_file_in_vscode(window_plot)
            if preview_opened:
                print(f"Run-all window overview opened in VS Code:\n  {window_plot}")
            else:
                print("Warning: Could not open the run-all window overview in VS Code automatically.")
                print(f"Run-all window overview file:\n  {window_plot}")
        else:
            print(f"Warning: Run-all window overview was not found:\n  {window_plot}")

        resonators_by_label = {str(r["label"]).upper(): r for r in resonators}
        changed = False
        print("\nReview run-all windows before measurement.")
        print("Format: C60002 5.98:6.02 (GHz). Enter a blank line when finished.")
        try:
            while True:
                try:
                    raw_override = input("Window override: ").strip()
                except EOFError:
                    raw_override = ""
                if not raw_override:
                    break
                try:
                    label, raw_range = raw_override.split(None, 1)
                    label = label.upper()
                    if label not in resonators_by_label:
                        available = ", ".join(sorted(resonators_by_label))
                        raise ValueError(f"unknown resonator '{label}' (available: {available})")
                    left, right = raw_range.replace(",", ":").split(":", 1)
                    range_start_ghz, range_stop_ghz = sorted((float(left), float(right)))
                    if range_start_ghz == range_stop_ghz:
                        raise ValueError("start and stop must differ")
                    if range_start_ghz <= 0:
                        raise ValueError("frequencies must be positive")

                    frequency = resonators_by_label[label]["frequency"]
                    frequency["start"] = range_start_ghz * 1e9
                    frequency["stop"] = range_stop_ghz * 1e9
                    review_context = getattr(self, "_window_review_context", None)
                    if review_context:
                        for resonator in review_context["refined_resonators"]:
                            if str(resonator["label"]).upper() == label:
                                resonator["start"] = range_start_ghz * 1e9
                                resonator["stop"] = range_stop_ghz * 1e9
                                break
                        self.reporter.save_resonator_window_overview(
                            base_data_dir,
                            review_context["refined_resonators"],
                            review_context["cached_sweeps"],
                            review_context["vna_port"],
                        )
                        self._focus_file_in_vscode(window_plot)
                    changed = True
                    print(
                        f"  Updated {label}: {range_start_ghz:.9f} to "
                        f"{range_stop_ghz:.9f} GHz"
                    )
                except (ValueError, KeyError) as exc:
                    print(f"  Invalid window override '{raw_override}': {exc}")
        finally:
            if preview_opened:
                if self._close_vscode_preview(window_plot):
                    print("Run-all window overview closed in VS Code.")
                else:
                    print("Warning: Could not close the VS Code window overview automatically.")

        if changed:
            self.cfg.save_toml(self.cfg.res_pd_config, self.file_res_pd)
            self.res_pd_config = self.cfg.res_pd_config
            print("Run-all window overrides saved to resonator_PD.toml.")
        else:
            print("Run-all windows left unchanged.")

    def run_power_sweep(self):
        """
        Executes the compiled power sweep tasks list, storing NC files.
        """
        print("\n" + "="*60)
        print("PHASE 4: EXECUTE POWER SWEEP")
        print("="*60)
        
        if not os.path.exists(self.file_power_task):
            print(f"Error: Compiled sweep file {self.file_power_task} not found. Please compile tasks first.")
            return
            
        with open(self.file_power_task, 'r', encoding='utf-8') as f:
            sweep_config = tomlkit.parse(f.read())
            
        vna_address = sweep_config["hardware"]["address"]
        vna_model = sweep_config["hardware"]["model"]
        vna_port = sweep_config["hardware"]["port"]
        attenuation = sweep_config["hardware"]["attenuation"]
        measurements = sweep_config["measurement"]
        
        self.driver.connect()
        first_window_sweeps = {}
        
        try:
            self.driver.setup_measurement(vna_port)
            for m_idx, m_task in enumerate(measurements):
                label = m_task["label"]
                output_folder = m_task["output"]
                freq_start = m_task["frequency"]["start"]
                freq_stop = m_task["frequency"]["stop"]
                sweep_point = m_task["frequency"]["points"]
                vna_power = m_task["power"]
                IF_bandwidth = m_task["IF_bandwidth"]
                repeat = m_task.get("repeat", 1)
                
                print(f"Task {m_idx + 1}/{len(measurements)}: Resonator {label} at {vna_power} dBm (repeat={repeat})...", end="\r")
                
                for i in range(repeat):
                    start_time = datetime.now()
                    
                    freq_array, s_params = self.driver.measure_sweep(
                        freq_start, freq_stop, sweep_point, vna_port, vna_power, IF_bandwidth
                    )
                    if label not in first_window_sweeps:
                        first_window_sweeps[label] = {
                            "frequency": np.array(freq_array, copy=True),
                            "s_params": np.array(s_params, copy=True),
                            "power": float(vna_power)
                        }
                    
                    end_time = datetime.now()
                    
                    attrs = {
                        "IF_bandwidth": int(IF_bandwidth),
                        "power": float(vna_power),
                        "attenuation": int(attenuation),
                        "port": str(vna_port),
                        "start_time": str(start_time.strftime("%Y%m%d_%H%M%S")),
                        "end_time": str(end_time.strftime("%Y%m%d_%H%M%S"))
                    }
                    
                    file_path = f"{output_folder}/{label}_{start_time.strftime('%Y%m%d_%H%M%S')}_{i+1:02d}.nc"
                    self.reporter.save_sweep_netcdf(file_path, freq_array, s_params, attrs, vna_port)
            # Print a final newline to clear the carriage return line
            print()
            base_data_dir = self.cfg.res_pd_config.get("output", {}).get("data_path", "data/raw")
            self.reporter.generate_run_all_window_overview(base_data_dir, first_window_sweeps, vna_port)
        finally:
            self.driver.disconnect()

    def run_batch_fitting(self):
        """
        Delegates Phase 5 batch circle fitting to the BatchFitter.
        """
        self.fitter.run_batch_fitting()

    def run_tls_analysis(self):
        """
        Delegates Phase 6 TLS loss fitting to the TLSAnalyzer.
        """
        self.tls_analyzer.run_tls_analysis()


def main():
    parser = argparse.ArgumentParser(description="Unified VNA Resonator Measurement Orchestrator")
    parser.add_argument("--find-windows", action="store_true", help="Run optimized peak finding and windowing (Phase 1 & 2)")
    parser.add_argument("--compile-tasks", action="store_true", help="Compile power-dependent SNR-adaptive task list (Phase 3)")
    parser.add_argument("--run-sweep", action="store_true", help="Execute the VNA power sweep (Phase 4)")
    parser.add_argument("--fit", action="store_true", help="Perform batch circle fitting on measured data (Phase 5)")
    parser.add_argument("--tls-fit", action="store_true", help="Perform TLS saturation loss fitting on fitted resonator data (Phase 6)")
    parser.add_argument("--run-all", action="store_true", help="Run full orchestrator pipeline (Phase 1 to 6)")
    parser.add_argument("--expected-dips", type=int, default=None, help="Expected number of dips to find in the sweep range")
    parser.add_argument("--dummy", action="store_true", help="Force VNA model to DUMMY for offline testing")
    parser.add_argument("--config-dir", type=str, default=None, help="Directory containing configuration TOML files")
    
    # Blind search options
    parser.add_argument("--blind-search", action="store_true", help="Perform a blind search for resonators across a frequency range")
    parser.add_argument("--start-freq", type=float, default=None, help="Blind search start frequency in GHz")
    parser.add_argument("--stop-freq", type=float, default=None, help="Blind search stop frequency in GHz")
    parser.add_argument("--prominence", type=str, default=None, help="Prominence threshold in dB for finding dips (can be float or 'auto')")
    parser.add_argument("--manual-rescue", action="store_true", help="After automatic blind search, interactively add user-selected GHz windows using their minimum points")
    parser.add_argument("--manual-range", action="append", default=[], metavar="START:STOP", help="Force-add the minimum from a GHz window; may be supplied multiple times")
    parser.add_argument("--sample-name", type=str, default=None, help="Automatically override the sample name in configurations")
    parser.add_argument("--vna-ip", type=str, default=None, help="Automatically override the VNA IP address or VISA address in configurations")
    parser.add_argument("--port", type=str, default=None, help="Override the measured S-parameter port (e.g. S21, S11, S22... S44) in configurations")
    
    args = parser.parse_args()

    parsed_manual_ranges = []
    for raw_range in args.manual_range:
        try:
            left, right = raw_range.replace(",", ":").split(":", 1)
            range_start, range_stop = sorted((float(left), float(right)))
            if range_start == range_stop:
                raise ValueError("start and stop must differ")
            parsed_manual_ranges.append((range_start * 1e9, range_stop * 1e9))
        except ValueError as exc:
            parser.error(f"invalid --manual-range '{raw_range}': {exc}")
    
    # Initialize Orchestrator
    orchestrator = VNAOrchestrator(args.config_dir)
    
    # Load defaults from execution/blind_search section of vna.toml if not provided via CLI
    exec_config = orchestrator.vna_config.get("execution", {})
    manual_rescue_config = orchestrator.vna_config.get("manual_rescue", {})
    if not args.manual_rescue and manual_rescue_config.get("enabled", False):
        args.manual_rescue = True
    
    # Dummy mode override
    if not args.dummy and exec_config.get("dummy", False):
        args.dummy = True
        
    # Sample name override (checks execution.sample_name first, then falls back to sample.name)
    if not args.sample_name:
        args.sample_name = exec_config.get("sample_name", orchestrator.vna_config.get("sample", {}).get("name", None))
        
    # Expected dips override
    if args.expected_dips is None:
        args.expected_dips = exec_config.get("expected_dips", None)
        
    # Blind search default overrides
    blind_config = orchestrator.vna_config.get("blind_search", {})
    if args.start_freq is None:
        args.start_freq = float(blind_config.get("start_freq_ghz", 4.0))
    if args.stop_freq is None:
        args.stop_freq = float(blind_config.get("stop_freq_ghz", 8.0))
    prom_val = args.prominence
    if prom_val is None:
        prom_val = blind_config.get("prominence_db", "auto")
    
    if isinstance(prom_val, str):
        prom_val_str = prom_val.strip().lower()
        if prom_val_str == "auto" or prom_val_str == "":
            args.prominence = "auto"
        else:
            try:
                args.prominence = float(prom_val)
            except ValueError:
                args.prominence = "auto"
    else:
        args.prominence = float(prom_val) if prom_val is not None else "auto"
        
    # Action override
    action = exec_config.get("action", None)
    if action and not (args.find_windows or args.compile_tasks or args.run_sweep or args.fit or args.tls_fit or args.run_all or args.blind_search):

        if action == "run-all":
            args.run_all = True
        elif action == "blind-search":
            args.blind_search = True
        elif action == "find-windows":
            args.find_windows = True
        elif action == "compile":
            args.compile_tasks = True
        elif action == "sweep":
            args.run_sweep = True
        elif action == "fit":
            args.fit = True
        elif action == "tls-fit":
            args.tls_fit = True
 
    # If still no action is specified, default to running the full pipeline (--run-all) with blind search
    if not (args.find_windows or args.compile_tasks or args.run_sweep or args.fit or args.tls_fit or args.run_all or args.blind_search):
        print("No action specified in CLI or config. Defaulting to running the full pipeline (--run-all) with blind search.")
        args.run_all = True
    
    # Determine sample name (use override, existing non-default, or generate a timestamped default)
    sample_name = args.sample_name
    if not sample_name:
        current_name = orchestrator.res_pd_config.get("sample", {}).get("name", "")
        # If the sample name is empty, default, or a mock placeholder, generate a timestamped default
        if not current_name:
            sample_name = f"sample_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            print(f"No sample name specified. Automatically generated sample name: {sample_name}")
        else:
            sample_name = current_name
            
    if sample_name:
        print(f"Overriding sample name in configurations to: {sample_name}")
        if "sample" in orchestrator.vna_config:
            orchestrator.vna_config["sample"]["name"] = sample_name
        if "sample" in orchestrator.res_pd_config:
            orchestrator.res_pd_config["sample"]["name"] = sample_name
            
    dynamic_data_path = ""
    # Set dynamic data path only if we are starting a new measurement/search workflow
    # (prevents overriding the data path during standalone fits or sweeps of existing directories)

    # edited by Ratis, tring to save the data in a fixed path "~/Resonator_Q_RawData", 2026-09-02
    data_path = os.path.join(Path.home(),"Resonator_Q_RawData")
    os.makedirs(data_path, exist_ok=True)

    generate_new_timestamp = args.run_all or args.blind_search or args.find_windows
    if generate_new_timestamp:
        run_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        # dynamic_data_path = f"data/{sample_name}_{run_timestamp}"
        dynamic_data_path = os.path.join(data_path, f"{sample_name}_{run_timestamp}") # Ratis edited 2026-09-02
        print(f"Dynamically setting base output data path to: {dynamic_data_path}")
        if "output" not in orchestrator.res_pd_config:
            orchestrator.res_pd_config["output"] = tomlkit.table()
        orchestrator.res_pd_config["output"]["data_path"] = dynamic_data_path
    # Set up logging to console + file
    if generate_new_timestamp:
        log_dir = dynamic_data_path
    else:
        log_dir = orchestrator.res_pd_config.get("output", {}).get("data_path", "data/raw")
        
    logger = TerminalLogger(log_dir)
    try:
        # Physically save configs
        orchestrator._save_toml(orchestrator.vna_config, orchestrator.file_vna_config)
        orchestrator._save_toml(orchestrator.res_pd_config, orchestrator.file_res_pd)
            
        if args.vna_ip:
            visa_address = args.vna_ip
            if "::" not in visa_address:
                visa_address = f"TCPIP0::{visa_address}::inst0::INSTR"
            print(f"Overriding VNA address to: {visa_address}")
            if "hardware" in orchestrator.vna_config:
                orchestrator.vna_config["hardware"]["address"] = visa_address
            if "hardware" in orchestrator.res_pd_config:
                orchestrator.res_pd_config["hardware"]["address"] = visa_address
            # Physically save configs
            orchestrator._save_toml(orchestrator.vna_config, orchestrator.file_vna_config)
            orchestrator._save_toml(orchestrator.res_pd_config, orchestrator.file_res_pd)
            
        if args.port:
            port_val = args.port.upper()
            import re
            if not re.match(r'^S[1-4][1-4]$', port_val):
                print(f"Warning: Specified port '{args.port}' does not match standard S-parameter format (e.g. S11, S21, S22... S44). Proceeding anyway.")
            print(f"Overriding VNA port in configurations to: {port_val}")
            if "hardware" in orchestrator.vna_config:
                orchestrator.vna_config["hardware"]["port"] = port_val
            if "hardware" in orchestrator.res_pd_config:
                orchestrator.res_pd_config["hardware"]["port"] = port_val
            # Physically save configs
            orchestrator._save_toml(orchestrator.vna_config, orchestrator.file_vna_config)
            orchestrator._save_toml(orchestrator.res_pd_config, orchestrator.file_res_pd)
            
        # Override settings for dummy offline test if requested (keeps it local to execution)
        if args.dummy:
            print("[Offline mode] Overriding VNA Model to DUMMY...")
            if "hardware" not in orchestrator.vna_config:
                orchestrator.vna_config["hardware"] = tomlkit.table()
            if "hardware" not in orchestrator.res_pd_config:
                orchestrator.res_pd_config["hardware"] = tomlkit.table()
            orchestrator.vna_config["hardware"]["model"] = "DUMMY"
            orchestrator.vna_config["hardware"]["address"] = "DUMMY_VISA_ADDRESS"
            orchestrator.res_pd_config["hardware"]["model"] = "DUMMY"
            orchestrator.res_pd_config["hardware"]["address"] = "DUMMY_VISA_ADDRESS"
            
        if args.run_all or args.blind_search:
            # Run blind search
            orchestrator.blind_search(
                args.start_freq * 1e9, args.stop_freq * 1e9,
                expected_count=args.expected_dips, prominence=args.prominence,
                manual_ranges=parsed_manual_ranges, interactive_manual=args.manual_rescue
            )
        elif args.find_windows:
            # Run manual legacy window finding from TOML
            orchestrator.find_all_windows(expected_dips_count=args.expected_dips)

        if args.run_all:
            orchestrator.review_run_all_windows()
            
        if args.compile_tasks or args.run_all:
            orchestrator.compile_power_tasks()
            
        if args.run_sweep or args.run_all:
            orchestrator.run_power_sweep()
            
        if args.fit or args.run_all:
            orchestrator.run_batch_fitting()
            
        if args.tls_fit or (args.run_all and orchestrator.vna_config.get("tls_analysis", {}).get("enabled", True)):
            orchestrator.run_tls_analysis()
    finally:
        logger.close()

if __name__ == "__main__":
    main()
