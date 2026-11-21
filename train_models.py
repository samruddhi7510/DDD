"""
Model Training and ONNX Export Script for MobileNetV2 and YOLOv11n-cls.
Trains on the Driver Drowsiness Dataset (DDD) located in splitted_dataset/
and exports lightweight ONNX models for real-time mobile inference.
"""

import os
import sys
import argparse
import numpy as np


def train_mobilenetv2(dataset_dir: str, output_onnx: str = "models/mobilenetv2_drowsiness.onnx", quick_mode: bool = True):
    """
    Fine-tunes MobileNetV2 on the Driver Drowsiness Dataset and exports to ONNX.
    """
    print("=" * 60)
    print("Starting MobileNetV2 Training Pipeline...")
    print(f"Dataset path: {dataset_dir}")
    print(f"Target ONNX output: {output_onnx}")
    print(f"Mode: {'Quick (Fast Feature Extraction)' if quick_mode else 'Full Training'}")
    print("=" * 60)
    
    try:
        import tensorflow as tf
        from tensorflow.keras.applications import MobileNetV2
        from tensorflow.keras.layers import Dense, Flatten, Dropout, GlobalAveragePooling2D
        from tensorflow.keras.models import Model
        from tensorflow.keras.preprocessing.image import ImageDataGenerator
        from tensorflow.keras.optimizers import Adam
        
        # Verify dataset paths
        train_dir = os.path.join(dataset_dir, "train")
        val_dir = os.path.join(dataset_dir, "val")
        
        if not os.path.exists(train_dir):
            raise FileNotFoundError(f"Training directory not found at {train_dir}")
            
        img_size = (224, 224)
        batch_size = 32 if quick_mode else 64
        epochs = 3 if quick_mode else 10
        
        # Data loaders with standard normalization [-1, 1] for MobileNetV2
        datagen = ImageDataGenerator(
            preprocessing_function=tf.keras.applications.mobilenet_v2.preprocess_input,
            horizontal_flip=True
        )
        val_datagen = ImageDataGenerator(
            preprocessing_function=tf.keras.applications.mobilenet_v2.preprocess_input
        )
        
        train_gen = datagen.flow_from_directory(
            train_dir,
            target_size=img_size,
            batch_size=batch_size,
            class_mode='categorical',
            shuffle=True
        )
        val_gen = val_datagen.flow_from_directory(
            val_dir,
            target_size=img_size,
            batch_size=batch_size,
            class_mode='categorical',
            shuffle=False
        )
        
        print(f"Classes detected: {train_gen.class_indices}")
        
        # Build MobileNetV2 Transfer Learning Architecture
        base_model = MobileNetV2(weights='imagenet', include_top=False, input_shape=(224, 224, 3))
        # Freeze base model layers for fast training
        base_model.trainable = False
        
        x = base_model.output
        x = GlobalAveragePooling2D()(x)
        x = Dense(256, activation='relu')(x)
        x = Dropout(0.3)(x)
        predictions = Dense(2, activation='softmax')(x)
        
        model = Model(inputs=base_model.input, outputs=predictions)
        model.compile(optimizer=Adam(learning_rate=0.001), loss='categorical_crossentropy', metrics=['accuracy'])
        
        steps_per_epoch = 50 if quick_mode else len(train_gen)
        val_steps = 20 if quick_mode else len(val_gen)
        
        print(f"Training for {epochs} epochs ({steps_per_epoch} steps/epoch)...")
        model.fit(
            train_gen,
            steps_per_epoch=steps_per_epoch,
            validation_data=val_gen,
            validation_steps=val_steps,
            epochs=epochs
        )
        
        # Save Keras Model
        os.makedirs(os.path.dirname(output_onnx), exist_ok=True)
        keras_path = output_onnx.replace(".onnx", ".keras")
        model.save(keras_path)
        print(f"Saved Keras model to {keras_path}")
        
        # Convert to ONNX
        try:
            import tf2onnx
            spec = (tf.TensorSpec((None, 224, 224, 3), tf.float32, name="input"),)
            model_proto, _ = tf2onnx.convert.from_keras(model, input_signature=spec, output_path=output_onnx)
            print(f"Exported MobileNetV2 ONNX to {output_onnx}")
        except ImportError:
            print("tf2onnx not installed; saved .keras model. To convert: pip install tf2onnx")
            
    except Exception as e:
        print(f"Error during MobileNetV2 training: {e}")


def train_yolov11(dataset_dir: str, output_onnx: str = "models/yolov11n_drowsiness.onnx", epochs: int = 5):
    """
    Fine-tunes YOLOv11n-cls using Ultralytics and exports to ONNX.
    """
    print("=" * 60)
    print("Starting YOLOv11 Classification Training Pipeline...")
    print(f"Dataset path: {dataset_dir}")
    print(f"Target ONNX output: {output_onnx}")
    print("=" * 60)
    
    try:
        from ultralytics import YOLO
        
        model = YOLO("yolo11n-cls.pt")
        print("Loaded base YOLO11n-cls architecture.")
        
        # Train on the dataset directory
        results = model.train(data=dataset_dir, epochs=epochs, imgsz=224, batch=32)
        print("YOLOv11 training complete!")
        
        # Export to ONNX format
        exported_path = model.export(format="onnx", imgsz=224)
        print(f"Exported YOLOv11 to ONNX: {exported_path}")
        
        # Copy to target path
        import shutil
        os.makedirs(os.path.dirname(output_onnx), exist_ok=True)
        shutil.copy(exported_path, output_onnx)
        print(f"Copied final YOLO ONNX to {output_onnx}")
        
    except Exception as e:
        print(f"Error during YOLOv11 training: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train MobileNetV2 and YOLOv11 on DDD Dataset")
    parser.add_argument("--dataset", type=str, default="D:\\safedrive_drowsiness_detection-master\\splitted_dataset", help="Path to splitted_dataset")
    parser.add_argument("--model", type=str, choices=["mobilenet", "yolo", "both"], default="both", help="Which model to train")
    parser.add_argument("--quick", action="store_true", help="Quick mode for testing")
    args = parser.parse_args()
    
    if args.model in ["mobilenet", "both"]:
        train_mobilenetv2(args.dataset, quick_mode=args.quick)
        
    if args.model in ["yolo", "both"]:
        train_yolov11(args.dataset, epochs=3 if args.quick else 10)
