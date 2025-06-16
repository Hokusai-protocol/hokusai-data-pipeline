#!/usr/bin/env python3
"""
Hokusai Preview CLI Tool

A command-line tool for running local performance previews of contributed data.
"""

import argparse
import sys
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.preview.data_loader import PreviewDataLoader
from src.preview.model_manager import PreviewModelManager
from src.preview.fine_tuner import PreviewFineTuner
from src.preview.evaluator import PreviewEvaluator
from src.preview.output_formatter import PreviewOutputFormatter


class PreviewPipeline:
    """Main preview pipeline orchestrator."""
    
    def __init__(
        self,
        test_mode: bool = False,
        verbose: bool = False,
        random_seed: int = 42
    ):
        """
        Initialize PreviewPipeline.
        
        Args:
            test_mode: Whether to run in test mode with mock baseline
            verbose: Whether to enable verbose output
            random_seed: Random seed for reproducibility
        """
        self.test_mode = test_mode
        self.verbose = verbose
        self.random_seed = random_seed
        
        # Initialize components
        self.data_loader = PreviewDataLoader(
            show_progress=verbose,
            random_seed=random_seed
        )
        self.model_manager = PreviewModelManager()
        self.fine_tuner = PreviewFineTuner(
            show_progress=verbose,
            random_seed=random_seed
        )
        self.evaluator = PreviewEvaluator()
        self.formatter = PreviewOutputFormatter()
        
        # Set up logging
        self._setup_logging()
        
    def run(
        self,
        data_path: Path,
        baseline_model: Optional[Path] = None,
        output_file: Optional[Path] = None,
        output_format: str = 'pretty'
    ) -> Dict[str, Any]:
        """
        Run the complete preview pipeline.
        
        Args:
            data_path: Path to contributed data file
            baseline_model: Optional path to baseline model
            output_file: Optional output file path
            output_format: Output format ('json' or 'pretty')
            
        Returns:
            Results dictionary
        """
        start_time = time.time()
        
        if self.verbose:
            print(f"Starting preview pipeline...")
            print(f"Data path: {data_path}")
            print(f"Output format: {output_format}")
            
        try:
            # Step 1: Load and validate data
            if self.verbose:
                print("\n1. Loading data...")
            data = self.data_loader.load_data(data_path)
            original_size = len(data)
            sample_size = min(len(data), self.data_loader.max_samples)
            
            # Step 2: Load baseline model
            if self.verbose:
                print("\n2. Loading baseline model...")
            if self.test_mode or baseline_model is None:
                baseline = self.model_manager.create_mock_baseline()
                baseline_model_type = "mock_baseline"
            else:
                baseline = self.model_manager.load_baseline_model(baseline_model)
                baseline_model_type = getattr(baseline, 'model_type', 'unknown')
                
            baseline_metrics = self.model_manager.get_model_metrics(baseline)
            
            # Step 3: Fine-tune model
            if self.verbose:
                print("\n3. Fine-tuning model...")
            new_model, training_history = self.fine_tuner.fine_tune(baseline, data)
            
            # Step 4: Evaluate models
            if self.verbose:
                print("\n4. Evaluating models...")
            
            # Create test split (use remaining data or resample)
            test_data = data.sample(n=min(1000, len(data) // 4), random_state=self.random_seed)
            
            new_metrics = self.evaluator.evaluate_model(new_model, test_data)
            
            # Step 5: Calculate delta
            if self.verbose:
                print("\n5. Calculating delta...")
            comparison = self.evaluator.compare_models(baseline_metrics, new_metrics)
            confidence = self.evaluator.estimate_confidence(sample_size)
            
            # Step 6: Format output
            end_time = time.time()
            elapsed_time = end_time - start_time
            
            output_data = self._build_output_data(
                comparison=comparison,
                baseline_metrics=baseline_metrics,
                new_metrics=new_metrics,
                baseline_model_type=baseline_model_type,
                sample_size=sample_size,
                original_size=original_size,
                confidence=confidence,
                elapsed_time=elapsed_time,
                data_path=str(data_path)
            )
            
            # Output results
            if output_format == 'json':
                json_output = self.formatter.format_json(output_data)
                if output_file:
                    self.formatter.save_to_file(output_data, output_file)
                    if self.verbose:
                        print(f"\nOutput saved to: {output_file}")
                else:
                    print(json_output)
            else:  # pretty format
                self.formatter.format_pretty(output_data)
                if output_file:
                    self.formatter.save_to_file(output_data, output_file)
                    if self.verbose:
                        print(f"\nOutput also saved to: {output_file}")
            
            if self.verbose:
                print("Preview complete!")
                
            return {
                'success': True,
                'delta_one_score': comparison['delta_one_score'],
                'metrics': new_metrics,
                'baseline_model_type': baseline_model_type,
                'sample_size_used': sample_size,
                'original_data_size': original_size
            }
            
        except Exception as e:
            error_msg = f"Preview failed: {str(e)}"
            if self.verbose:
                import traceback
                print(f"\nError: {error_msg}")
                print(traceback.format_exc())
            else:
                print(f"Error: {error_msg}")
            
            return {
                'success': False,
                'error': error_msg
            }
            
    def _build_output_data(
        self,
        comparison: Dict[str, Any],
        baseline_metrics: Dict[str, float],
        new_metrics: Dict[str, float],
        baseline_model_type: str,
        sample_size: int,
        original_size: int,
        confidence: float,
        elapsed_time: float,
        data_path: str
    ) -> Dict[str, Any]:
        """Build the complete output data structure."""
        return {
            'schema_version': '1.0',
            'delta_computation': comparison,
            'baseline_model': {
                'model_id': '1.0.0',
                'model_type': baseline_model_type,
                'metrics': baseline_metrics
            },
            'new_model': {
                'model_id': 'preview_2.0.0',
                'model_type': 'fine_tuned_classifier',
                'metrics': new_metrics
            },
            'preview_metadata': {
                'preview_mode': True,
                'estimation_confidence': confidence,
                'sample_size_used': sample_size,
                'original_data_size': original_size,
                'time_elapsed': elapsed_time,
                'data_path': data_path,
                'timestamp': datetime.now().isoformat()
            }
        }
        
    def _setup_logging(self):
        """Set up logging configuration."""
        level = logging.DEBUG if self.verbose else logging.INFO
        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Hokusai Preview Tool - Local performance estimation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic preview with pretty output
  python hokusai_preview.py --data-path data.csv
  
  # Save JSON output to file
  python hokusai_preview.py --data-path data.csv --output-format json --output-file results.json
  
  # Use custom baseline model
  python hokusai_preview.py --data-path data.csv --baseline-model models/my_baseline.pkl
  
  # Verbose mode with test baseline
  python hokusai_preview.py --data-path data.csv --test-mode --verbose
        """
    )
    
    parser.add_argument(
        '--data-path',
        type=Path,
        required=True,
        help='Path to contributed data file (CSV, JSON, or Parquet)'
    )
    
    parser.add_argument(
        '--baseline-model',
        type=Path,
        help='Path to baseline model file (uses default if not specified)'
    )
    
    parser.add_argument(
        '--output-file',
        type=Path,
        help='Path to save output file'
    )
    
    parser.add_argument(
        '--output-format',
        choices=['json', 'pretty'],
        default='pretty',
        help='Output format (default: pretty)'
    )
    
    parser.add_argument(
        '--sample-size',
        type=int,
        default=10000,
        help='Maximum samples to use (default: 10000)'
    )
    
    parser.add_argument(
        '--test-mode',
        action='store_true',
        help='Use mock baseline model for testing'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    
    parser.add_argument(
        '--random-seed',
        type=int,
        default=42,
        help='Random seed for reproducibility (default: 42)'
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.data_path.exists():
        print(f"Error: Data file not found: {args.data_path}")
        sys.exit(1)
        
    if args.baseline_model and not args.baseline_model.exists():
        print(f"Error: Baseline model not found: {args.baseline_model}")
        sys.exit(1)
    
    # Update data loader max samples
    PreviewDataLoader.max_samples = args.sample_size
    
    # Create and run pipeline
    pipeline = PreviewPipeline(
        test_mode=args.test_mode,
        verbose=args.verbose,
        random_seed=args.random_seed
    )
    
    result = pipeline.run(
        data_path=args.data_path,
        baseline_model=args.baseline_model,
        output_file=args.output_file,
        output_format=args.output_format
    )
    
    # Exit with error code if failed
    if not result['success']:
        sys.exit(1)


if __name__ == '__main__':
    main()