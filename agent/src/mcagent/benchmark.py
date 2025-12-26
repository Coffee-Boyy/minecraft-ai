"""Benchmark runner for measuring agent performance."""

import asyncio
import json
import time
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn

from .bridge_client import BridgeClient
from .capture import ScreenCapture
from .config import Config
from .policy import VLMPolicy
from .protocol import AckMessage, StateMessage


class BenchmarkRunner:
    """Runs benchmarks to measure agent performance."""

    def __init__(self, config: Config, duration_seconds: int = 60):
        """
        Initialize the benchmark runner.

        Args:
            config: Agent configuration
            duration_seconds: How long to run the benchmark
        """
        self.config = config
        self.duration = duration_seconds
        self.console = Console()

        # Components
        self.capture = ScreenCapture(
            mode=config.capture_mode,
            target_resolution=config.capture_resolution,
            window_title=config.capture_window_title,
        )
        self.policy = VLMPolicy(config)
        self.bridge = BridgeClient(config.bridge_ws_url)

        # Metrics
        self.metrics: list[dict] = []
        self.latest_state: Optional[StateMessage] = None
        self.acks_received: int = 0

    async def run(self):
        """Run the benchmark."""
        self.console.print("[cyan]Starting benchmark...[/cyan]")
        self.console.print(f"Duration: {self.duration} seconds\n")

        # Set up callbacks
        self.bridge.set_state_callback(self._on_state)
        self.bridge.set_ack_callback(self._on_ack)

        # Connect to bridge
        try:
            await self.bridge.connect()
            self.console.print("[green]Connected to Minecraft bridge[/green]\n")
        except Exception as e:
            self.console.print(f"[red]Failed to connect: {e}[/red]")
            return

        # Start receiving messages
        receive_task = asyncio.create_task(self.bridge.receive_messages())

        # Run benchmark with progress display
        start_time = time.time()
        end_time = start_time + self.duration

        with Progress(
            SpinnerColumn(),
            *Progress.get_default_columns(),
            TimeElapsedColumn(),
            console=self.console,
        ) as progress:
            task = progress.add_task("[cyan]Running benchmark...", total=self.duration)

            while time.time() < end_time:
                await self._run_iteration(start_time)
                progress.update(task, completed=time.time() - start_time)
                await asyncio.sleep(0.01)  # Small sleep to prevent tight loop

        # Clean up
        receive_task.cancel()
        await self.bridge.close()
        self.capture.close()
        self.policy.close()

        # Analyze and display results
        self._analyze_results()

    async def _run_iteration(self, benchmark_start: float):
        """Execute one benchmark iteration."""
        try:
            # Capture frame
            t0 = time.perf_counter()
            frame = self.capture.capture_frame()
            t1 = time.perf_counter()
            t_capture_ms = (t1 - t0) * 1000

            # Convert to data URL
            image_data_url = self.capture.frame_to_png_base64(frame)

            # Get action from VLM
            t2 = time.perf_counter()
            # Offload sync HTTP to avoid blocking receive_messages() background task.
            action = await asyncio.to_thread(
                self.policy.get_action, image_data_url, "benchmark test", None
            )
            t3 = time.perf_counter()
            t_vlm_ms = (t3 - t2) * 1000

            # Send to bridge
            t4 = time.perf_counter()
            await self.bridge.send_action(action)
            t5 = time.perf_counter()
            t_ws_send_ms = (t5 - t4) * 1000

            # Calculate end-to-end time (capture + VLM + send)
            end_to_end_ms = t_capture_ms + t_vlm_ms + t_ws_send_ms

            # Record metrics
            self.metrics.append(
                {
                    "timestamp": time.time() - benchmark_start,
                    "t_capture_ms": t_capture_ms,
                    "t_vlm_ms": t_vlm_ms,
                    "t_ws_send_ms": t_ws_send_ms,
                    "end_to_end_ms": end_to_end_ms,
                }
            )

        except Exception as e:
            self.console.print(f"[red]Error in iteration: {e}[/red]")

    def _on_state(self, state: StateMessage):
        """Callback for state updates."""
        self.latest_state = state

    def _on_ack(self, ack: AckMessage):
        """Callback for action acknowledgments."""
        # Track acks received regardless of success, since this is primarily a
        # transport/round-trip metric.
        self.acks_received += 1

    def _analyze_results(self):
        """Analyze and display benchmark results."""
        if not self.metrics:
            self.console.print("[red]No metrics collected[/red]")
            return

        complete_metrics = self.metrics

        # Calculate statistics
        n = len(complete_metrics)
        capture_times = [m["t_capture_ms"] for m in complete_metrics]
        vlm_times = [m["t_vlm_ms"] for m in complete_metrics]
        send_times = [m["t_ws_send_ms"] for m in complete_metrics]
        e2e_times = [m["end_to_end_ms"] for m in complete_metrics]

        def calc_stats(values):
            if not values:
                return {"mean": 0, "min": 0, "max": 0, "p50": 0, "p95": 0}
            sorted_vals = sorted(values)
            return {
                "mean": sum(values) / len(values),
                "min": min(values),
                "max": max(values),
                "p50": sorted_vals[len(sorted_vals) // 2],
                "p95": sorted_vals[int(len(sorted_vals) * 0.95)],
            }

        capture_stats = calc_stats(capture_times)
        vlm_stats = calc_stats(vlm_times)
        send_stats = calc_stats(send_times)
        e2e_stats = calc_stats(e2e_times)

        # Calculate effective Hz
        effective_hz = 1000.0 / e2e_stats["mean"] if e2e_stats["mean"] > 0 else 0

        # Display results
        self.console.print("\n[cyan]Benchmark Results:[/cyan]\n")
        self.console.print(f"Total iterations: {len(self.metrics)}")
        self.console.print(f"Acks received: {self.acks_received}\n")

        self.console.print("[yellow]Capture times (ms):[/yellow]")
        self._print_stats(capture_stats)

        self.console.print("\n[yellow]VLM inference times (ms):[/yellow]")
        self._print_stats(vlm_stats)

        self.console.print("\n[yellow]WebSocket send times (ms):[/yellow]")
        self._print_stats(send_stats)

        if e2e_times:
            self.console.print("\n[yellow]End-to-end times (ms):[/yellow]")
            self._print_stats(e2e_stats)
            self.console.print(f"\n[green]Effective Hz: {effective_hz:.2f}[/green]")

            # Check acceptance criteria
            self._check_acceptance_criteria(e2e_stats, effective_hz)

        # Save to file
        self._save_results(complete_metrics, e2e_stats, effective_hz)

    def _print_stats(self, stats: dict):
        """Print statistics in a formatted way."""
        self.console.print(f"  Mean: {stats['mean']:.2f}")
        self.console.print(f"  Min:  {stats['min']:.2f}")
        self.console.print(f"  Max:  {stats['max']:.2f}")
        self.console.print(f"  P50:  {stats['p50']:.2f}")
        self.console.print(f"  P95:  {stats['p95']:.2f}")

    def _check_acceptance_criteria(self, e2e_stats: dict, effective_hz: float):
        """Check if results meet acceptance criteria."""
        self.console.print("\n[cyan]Acceptance Criteria:[/cyan]")

        # Criteria: < 250ms at 3+ Hz OR < 400ms at 2+ Hz
        if e2e_stats["mean"] < 250 and effective_hz >= 3.0:
            self.console.print("[green]✓ PASS: < 250ms and >= 3 Hz[/green]")
        elif e2e_stats["mean"] < 400 and effective_hz >= 2.0:
            self.console.print("[green]✓ PASS: < 400ms and >= 2 Hz[/green]")
        else:
            self.console.print("[red]✗ FAIL: Does not meet latency/Hz criteria[/red]")

    def _save_results(self, metrics: list[dict], e2e_stats: dict, effective_hz: float):
        """Save results to JSONL file."""
        log_dir = Path(__file__).parent.parent.parent / "logs"
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / "bench.jsonl"

        # Write summary
        summary = {
            "timestamp": time.time(),
            "duration_seconds": self.duration,
            "total_iterations": len(self.metrics),
            "complete_measurements": len(metrics),
            "e2e_stats_ms": e2e_stats,
            "effective_hz": effective_hz,
            "config": {
                "capture_fps": self.config.capture_fps,
                "decision_hz": self.config.decision_hz,
                "max_new_tokens": self.config.max_new_tokens,
            },
        }

        with open(log_file, "a") as f:
            f.write(json.dumps(summary) + "\n")

        self.console.print(f"\n[cyan]Results saved to: {log_file}[/cyan]")
