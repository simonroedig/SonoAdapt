import os
import torch
from transformers import CLIPModel, ClapModel

# This file was used to export the CLIP and CLAP model from the AudioAdapt Python Code-Base
# to Onnx models to be used in the Android Application. 

def export_clip(output_path="clip_image_model.onnx", quantized_path="clip_image_model_quantized.onnx"):
    print("Loading CLIP model...")
    model_name = "openai/clip-vit-base-patch32"
    model = CLIPModel.from_pretrained(model_name).eval()
    
    # We only need the image features part
    # get_image_features takes pixel_values of shape (batch, channels, height, width)
    # The default processor resizes to 224x224
    dummy_input = torch.randn(1, 3, 224, 224)
    
    print(f"Exporting CLIP image model to {output_path}...")
    
    # To export just the image branch, we can wrap the get_image_features method
    class CLIPImageWrapper(torch.nn.Module):
        def __init__(self, clip_model):
            super().__init__()
            self.clip_model = clip_model
            
        def forward(self, pixel_values):
            return self.clip_model.get_image_features(pixel_values=pixel_values)
            
    wrapper = CLIPImageWrapper(model)
    
    torch.onnx.export(
        wrapper,
        dummy_input,
        output_path,
        export_params=True,
        opset_version=14,
        do_constant_folding=True,
        input_names=["pixel_values"],
        output_names=["image_features"],
        dynamic_axes={"pixel_values": {0: "batch_size"}, "image_features": {0: "batch_size"}}
    )
    
    print("Quantizing CLIP model...")
    try:
        from onnxruntime.quantization import quantize_dynamic, QuantType
        quantize_dynamic(
            model_input=output_path,
            model_output=quantized_path,
            weight_type=QuantType.QUInt8
        )
        print(f"Quantized CLIP saved to {quantized_path}")
    except ImportError:
        print("onnxruntime not installed. Skipping quantization.")

def export_clap(output_path="clap_audio_model.onnx", quantized_path="clap_audio_model_quantized.onnx"):
    print("Loading CLAP model...")
    model_name = "laion/clap-htsat-unfused"
    model = ClapModel.from_pretrained(model_name).eval()
    
    # Clap audio processor typically produces input_features of shape (batch, 1, time, freq)
    # Let's use the processor to get the exact shape.
    from transformers import ClapProcessor
    import numpy as np
    
    processor = ClapProcessor.from_pretrained(model_name)
    dummy_audio = np.random.randn(48000 * 5) # 5 seconds of random noise
    inputs = processor(audios=dummy_audio, return_tensors="pt", sampling_rate=48000)
    dummy_input_features = inputs["input_features"]
    
    print(f"Dummy input shape: {dummy_input_features.shape}")
    
    print(f"Exporting CLAP audio model to {output_path}...")
    
    class CLAPAudioWrapper(torch.nn.Module):
        def __init__(self, clap_model):
            super().__init__()
            self.clap_model = clap_model
            
        def forward(self, input_features):
            return self.clap_model.get_audio_features(input_features=input_features)
            
    wrapper = CLAPAudioWrapper(model)
    
    torch.onnx.export(
        wrapper,
        dummy_input_features,
        output_path,
        export_params=True,
        opset_version=14,
        do_constant_folding=True,
        input_names=["input_features"],
        output_names=["audio_features"],
        dynamic_axes={"input_features": {0: "batch_size"}, "audio_features": {0: "batch_size"}}
    )
    
    print("Quantizing CLAP model...")
    try:
        from onnxruntime.quantization import quantize_dynamic, QuantType
        quantize_dynamic(
            model_input=output_path,
            model_output=quantized_path,
            weight_type=QuantType.QUInt8
        )
        print(f"Quantized CLAP saved to {quantized_path}")
    except ImportError:
        print("onnxruntime not installed. Skipping quantization.")

if __name__ == "__main__":
    import os
    # Ensure we have required libs
    try:
        import onnx
        import onnxruntime
    except ImportError:
        print("Please run: pip install onnx onnxruntime torch transformers numpy")
        import sys
        sys.exit(1)
        
    os.makedirs("onnx_models", exist_ok=True)
    export_clip(
        output_path="onnx_models/clip_image_model.onnx",
        quantized_path="onnx_models/clip_image_model_quantized.onnx"
    )
    export_clap(
        output_path="onnx_models/clap_audio_model.onnx",
        quantized_path="onnx_models/clap_audio_model_quantized.onnx"
    )
    print("Done! You can copy the quantized models to the Android assets folder.")
