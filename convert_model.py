#!/usr/bin/env python3
"""
Convert PyTorch model to ONNX format for Hailo deployment
"""

import torch
import torch.onnx
import sys
import os

def convert_pt_to_onnx(pt_path, onnx_path, input_size=(640, 640)):
    """
    Convert PyTorch model (.pt) to ONNX format
    
    Args:
        pt_path: Path to .pt model file
        onnx_path: Output path for .onnx file
        input_size: Model input size (height, width)
    """
    print(f"Loading PyTorch model from: {pt_path}")
    
    try:
        # Try loading as a full model first
        model = torch.load(pt_path, map_location='cpu')
        
        # If it's a dict with 'model' key (common YOLO format)
        if isinstance(model, dict):
            if 'model' in model:
                model = model['model']
            elif 'ema' in model:
                model = model['ema']
        
        # Handle ultralytics YOLO models
        if hasattr(model, 'float'):
            model = model.float()
        if hasattr(model, 'fuse'):
            model.fuse()
        
        model.eval()
        
    except Exception as e:
        print(f"Error loading model: {e}")
        print("Trying alternative loading method...")
        try:
            # Try loading with weights_only=True (PyTorch 2.0+)
            model = torch.load(pt_path, map_location='cpu', weights_only=False)
            if isinstance(model, dict) and 'model' in model:
                model = model['model']
            model.eval()
        except Exception as e2:
            print(f"Failed to load model: {e2}")
            sys.exit(1)
    
    print(f"Model loaded successfully")
    print(f"Model type: {type(model)}")
    
    # Create dummy input
    batch_size = 1
    height, width = input_size
    dummy_input = torch.randn(batch_size, 3, height, width)
    
    print(f"Creating dummy input: {dummy_input.shape}")
    print(f"Exporting to ONNX: {onnx_path}")
    
    # Export to ONNX
    try:
        torch.onnx.export(
            model,
            dummy_input,
            onnx_path,
            export_params=True,
            opset_version=11,
            do_constant_folding=True,
            input_names=['images'],
            output_names=['output'],
            dynamic_axes={
                'images': {0: 'batch_size'},
                'output': {0: 'batch_size'}
            }
        )
        print(f"✓ Successfully exported to: {onnx_path}")
        print(f"\nNext steps:")
        print(f"1. Transfer {onnx_path} to a machine with Hailo Dataflow Compiler")
        print(f"2. Run: hailo parser onnx {os.path.basename(onnx_path)}")
        print(f"3. Run: hailo optimize my_model.har")
        print(f"4. Run: hailo compiler my_model.har --hw-arch hailo8l")
        print(f"5. Transfer the resulting .hef file back to your robot")
        print(f"6. Update model_path parameter to point to your .hef file")
        
    except Exception as e:
        print(f"✗ Export failed: {e}")
        print("\nTrying with explicit output format...")
        
        # Try with forward pass to understand output
        with torch.no_grad():
            output = model(dummy_input)
            print(f"Model output shape: {output.shape if hasattr(output, 'shape') else type(output)}")
        
        sys.exit(1)

if __name__ == "__main__":
    # Paths
    pt_path = "my_model.pt"
    onnx_path = "my_model.onnx"
    
    # Check if input file exists
    if not os.path.exists(pt_path):
        print(f"Error: {pt_path} not found!")
        sys.exit(1)
    
    # Convert
    convert_pt_to_onnx(pt_path, onnx_path)
