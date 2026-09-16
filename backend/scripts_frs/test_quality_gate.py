import sys, os
sys.path.insert(0, os.path.abspath("."))
import numpy as np
import cv2
import ast

# 1. Syntax check
ast.parse(open("app/frs_engine/frs_service.py", encoding="utf-8").read())
ast.parse(open("app/frs_engine/recognition/quality.py", encoding="utf-8").read())
ast.parse(open("app/frs_engine/config.py", encoding="utf-8").read())
print("[OK] Syntax verification passed for all modified files!")

# 2. Test Quality Gate logic
from app.frs_engine.recognition.quality import FaceQualityAssessor

assessor = FaceQualityAssessor(min_sharpness=45.0, min_width=60, max_yaw=35.0)

# Create mock frame: 720x1280
frame = np.full((720, 1280, 3), 120, dtype=np.uint8)

# Test 1: Small Face (<60px, e.g. 25x25)
bbox_small = np.array([100, 100, 125, 125])
q_small = assessor.assess_quality(frame, bbox_small, pose=np.array([0.0, 0.0, 0.0]))
print(f"Test 1 - Small Face (25px)     : usable={q_small.is_usable} (expected=False)")
assert not q_small.is_usable, "Small face should be rejected"

# Test 2: Blurry Face (Gaussian blur applied, >=60px)
blurred_patch = cv2.GaussianBlur(np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8), (31, 31), 10)
frame[200:300, 200:300] = blurred_patch
bbox_blur = np.array([200, 200, 300, 300])
q_blur = assessor.assess_quality(frame, bbox_blur, pose=np.array([0.0, 0.0, 0.0]))
print(f"Test 2 - Blurry Face (blur={q_blur.blur_score}): usable={q_blur.is_usable} (expected=False)")
assert not q_blur.is_usable, "Blurry face should be rejected"

# Test 3: Extreme Pose (yaw = 48 deg, pitch = 10 deg)
bbox_pose = np.array([300, 300, 400, 400])
q_pose = assessor.assess_quality(frame, bbox_pose, pose=np.array([10.0, 48.0, 0.0]))
print(f"Test 3 - Extreme Pose (yaw=48): usable={q_pose.is_usable} (expected=False)")
assert not q_pose.is_usable, "Extreme pose face should be rejected"

# Test 4: Clear Sharp Frontal Face (100px, high texture/sharpness, frontal pose)
sharp_patch = np.zeros((100, 100, 3), dtype=np.uint8)
sharp_patch[::2, ::2] = 220
sharp_patch[1::2, 1::2] = 40
frame[400:500, 400:500] = sharp_patch
bbox_clear = np.array([400, 400, 500, 500])
q_clear = assessor.assess_quality(frame, bbox_clear, pose=np.array([5.0, 12.0, 2.0]))
print(f"Test 4 - Clear Frontal Face    : usable={q_clear.is_usable}, blur={q_clear.blur_score}, size={q_clear.face_width}x{q_clear.face_height} (expected=True)")
assert q_clear.is_usable, "Clear frontal face should be accepted"

print("\nALL FACE QUALITY TESTS PASSED SUCCESSFULLY!")
