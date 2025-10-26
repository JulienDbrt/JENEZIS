#!/usr/bin/env python3
"""
Mass Densification Engine - The Beast Feeder
Aggressively processes unmapped skills in progressive batches
"""

import json
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from typing import Any

import pandas as pd


class MassDensifier:
    def __init__(self) -> None:
        self.db_path = "ontology.db"
        self.unmapped_file = "data/output/unmapped_skills_analysis.csv"
        self.log_file = "data/output/densification_log.json"
        self.stats: dict[str, Any] = {
            "start_time": datetime.now().isoformat(),
            "total_unmapped": 0,
            "processed": 0,
            "success": 0,
            "failed": 0,
            "batches": [],
        }

    def get_current_stats(self) -> dict[str, int]:
        """Get current ontology statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        stats = {}
        stats["skills"] = cursor.execute("SELECT COUNT(*) FROM skills").fetchone()[0]
        stats["aliases"] = cursor.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
        stats["hierarchy"] = cursor.execute("SELECT COUNT(*) FROM hierarchy").fetchone()[0]

        conn.close()
        return stats

    def reload_api_cache(self) -> bool:
        """Trigger API cache reload"""
        try:
            import requests

            response = requests.post("http://127.0.0.1:8000/admin/reload", timeout=10)
            return response.status_code == 200
        except:
            print("⚠️  API not running - cache reload skipped")
            return False

    def run_densification(self, batch_size: int) -> bool:
        """Run densification for a batch"""
        print(f"\n🔥 Processing batch of {batch_size} skills...")

        start_stats = self.get_current_stats()

        # Run densification
        result = subprocess.run(
            ["poetry", "run", "python", "src/cli/densify_ontology.py", str(batch_size)],
            capture_output=True,
            text=True,
        )

        end_stats = self.get_current_stats()

        # Calculate gains
        gains = {
            "skills": end_stats["skills"] - start_stats["skills"],
            "aliases": end_stats["aliases"] - start_stats["aliases"],
            "hierarchy": end_stats["hierarchy"] - start_stats["hierarchy"],
        }

        batch_info = {
            "batch_size": batch_size,
            "timestamp": datetime.now().isoformat(),
            "gains": gains,
            "success": result.returncode == 0,
        }

        self.stats["batches"].append(batch_info)

        if result.returncode == 0:
            self.stats["success"] += gains["skills"]
            print(f"✅ Batch complete: +{gains['skills']} skills, +{gains['aliases']} aliases")
        else:
            self.stats["failed"] += batch_size
            print(f"❌ Batch failed: {result.stderr[:200]}")

        return result.returncode == 0

    def aggressive_mode(self) -> None:
        """Aggressive processing with progressive batch sizes"""
        print("🚀 AGGRESSIVE MODE ACTIVATED - THE BEAST AWAKENS")
        print("=" * 60)

        # Count total unmapped
        df = pd.read_csv(self.unmapped_file)
        self.stats["total_unmapped"] = len(df)
        print(f"📊 Total unmapped skills: {self.stats['total_unmapped']:,}")

        initial_stats = self.get_current_stats()
        print(
            f"📈 Initial ontology: {initial_stats['skills']} skills, {initial_stats['aliases']} aliases"
        )

        # Progressive batch strategy
        batch_strategy = [
            (10, 50),  # 10 batches of 50 (warm up)
            (10, 100),  # 10 batches of 100
            (5, 250),  # 5 batches of 250
            (4, 500),  # 4 batches of 500
            (2, 1000),  # 2 batches of 1000
        ]

        print("\n📋 Batch Strategy:")
        for count, size in batch_strategy:
            print(f"   - {count}x {size} skills = {count * size} total")

        total_planned = sum(count * size for count, size in batch_strategy)
        print(f"\n🎯 Total planned: {total_planned:,} skills")

        # Execute batches
        for batch_count, batch_size in batch_strategy:
            print(f"\n{'='*60}")
            print(f"🏭 Phase: {batch_count} batches of {batch_size} skills")
            print(f"{'='*60}")

            for i in range(batch_count):
                print(f"\n📦 Batch {i+1}/{batch_count}")

                success = self.run_densification(batch_size)
                self.stats["processed"] += batch_size

                # Reload API cache after each batch
                if success:
                    self.reload_api_cache()

                # Progressive delay to avoid rate limits
                delay = min(5 + (batch_size / 100), 30)
                print(f"⏰ Cooling down for {delay:.0f}s...")
                time.sleep(delay)

                # Show progress
                progress = (self.stats["processed"] / total_planned) * 100
                print(f"\n📊 Progress: {self.stats['processed']}/{total_planned} ({progress:.1f}%)")

                current_stats = self.get_current_stats()
                print(
                    f"📈 Current: {current_stats['skills']} skills (+{current_stats['skills'] - initial_stats['skills']})"
                )

        # Final statistics
        self.show_final_report(initial_stats)

    def show_final_report(self, initial_stats: dict[str, int]) -> None:
        """Display final report"""
        final_stats = self.get_current_stats()

        print("\n" + "=" * 60)
        print("🏁 DENSIFICATION COMPLETE - FINAL REPORT")
        print("=" * 60)

        duration = (
            datetime.now() - datetime.fromisoformat(self.stats["start_time"])
        ).total_seconds() / 60

        print(f"\n⏱️  Duration: {duration:.1f} minutes")
        print(f"📦 Batches processed: {len(self.stats['batches'])}")
        print(f"📊 Skills processed: {self.stats['processed']:,}")

        print("\n📈 Ontology Growth:")
        print(
            f"   Skills: {initial_stats['skills']} → {final_stats['skills']} (+{final_stats['skills'] - initial_stats['skills']})"
        )
        print(
            f"   Aliases: {initial_stats['aliases']} → {final_stats['aliases']} (+{final_stats['aliases'] - initial_stats['aliases']})"
        )
        print(
            f"   Relations: {initial_stats['hierarchy']} → {final_stats['hierarchy']} (+{final_stats['hierarchy'] - initial_stats['hierarchy']})"
        )

        growth_rate = (
            (final_stats["skills"] - initial_stats["skills"]) / initial_stats["skills"]
        ) * 100
        print(f"\n🎯 Growth Rate: {growth_rate:.1f}%")

        # Save log
        self.stats["end_time"] = datetime.now().isoformat()
        self.stats["final_stats"] = final_stats
        self.stats["growth"] = {
            "skills": final_stats["skills"] - initial_stats["skills"],
            "aliases": final_stats["aliases"] - initial_stats["aliases"],
            "hierarchy": final_stats["hierarchy"] - initial_stats["hierarchy"],
        }

        with open(self.log_file, "w") as f:
            json.dump(self.stats, f, indent=2)

        print(f"\n💾 Log saved to: {self.log_file}")

        # Estimate remaining work
        remaining = self.stats["total_unmapped"] - self.stats["processed"]
        if remaining > 0:
            print(f"\n⚠️  Remaining unmapped: ~{remaining:,} skills")
            print("   Run again to continue the feast!")


def main() -> None:
    """Main entry point"""
    print(
        """
╔══════════════════════════════════════════════════════════════╗
║           MASS DENSIFICATION ENGINE - THE BEAST              ║
║                  87,000 skills await conquest                ║
╚══════════════════════════════════════════════════════════════╝
    """
    )

    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        # Just show current stats
        densifier = MassDensifier()
        stats = densifier.get_current_stats()
        print(
            f"Current ontology: {stats['skills']} skills, {stats['aliases']} aliases, {stats['hierarchy']} relations"
        )
        return

    # Check if API is running
    try:
        import requests

        response = requests.get("http://127.0.0.1:8000/stats", timeout=10)
        if response.status_code == 200:
            print("✅ API is running")
        else:
            print("⚠️  API is not responding properly")
    except:
        print("⚠️  API is not running - cache reload will be skipped")
        print("   Consider running: poetry run uvicorn src.api.main:app --reload")

    # Confirm before starting
    print("\n⚡ This will run aggressive densification in progressive batches")
    print("   Estimated time: 30-60 minutes")

    # Auto-yes mode with --auto flag
    if len(sys.argv) > 1 and sys.argv[1] == "--auto":
        print("\n🤖 AUTO MODE ACTIVATED - Starting immediately!")
        user_response: str = "y"
    else:
        user_response = input("\nProceed? (y/n): ")

    if user_response.lower() == "y":
        densifier = MassDensifier()
        try:
            densifier.aggressive_mode()
        except KeyboardInterrupt:
            print("\n\n⚠️  Process interrupted by user")
            print("   Progress has been saved. Run again to continue.")
    else:
        print("Aborted.")


if __name__ == "__main__":
    main()
