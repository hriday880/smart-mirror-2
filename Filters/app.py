import cv2
import mediapipe as mp
import gradio as gr
import numpy as np

from hand_tracking import INDEX_TIP, THUMB_TIP
from geometry import render_portal, portal_width, ClosingGestureDetector
from filters import FILTROS

# Initialize MediaPipe Hands
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(
    max_num_hands=2,
    min_detection_confidence=0.6,
    min_tracking_confidence=0.6,
)

def process_frame(frame, filtro_index, closing_detector):
    if frame is None:
        return None, filtro_index, closing_detector

    h, w = frame.shape[:2]
    # Gradio passes RGB images, so we process directly
    results = hands.process(frame)

    left_hand = None
    right_hand = None

    if results.multi_hand_landmarks and results.multi_handedness:
        for hand_landmarks, handedness in zip(
            results.multi_hand_landmarks, results.multi_handedness
        ):
            raw_label = handedness.classification[0].label
            label = "Right" if raw_label == "Left" else "Left"

            if label == "Left":
                left_hand = hand_landmarks
            else:
                right_hand = hand_landmarks

    # The filter functions expect BGR, so we need to pass a BGR copy to render_portal
    bgr_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

    if left_hand is not None and right_hand is not None:
        lm_left = left_hand.landmark
        lm_right = right_hand.landmark

        p1 = (lm_left[INDEX_TIP].x * w, lm_left[INDEX_TIP].y * h)
        p2 = (lm_left[THUMB_TIP].x * w, lm_left[THUMB_TIP].y * h)
        p3 = (lm_right[INDEX_TIP].x * w, lm_right[INDEX_TIP].y * h)
        p4 = (lm_right[THUMB_TIP].x * w, lm_right[THUMB_TIP].y * h)

        width = portal_width(p1, p2, p3, p4)

        if closing_detector.update(width, w):
            filtro_index = (filtro_index + 1) % len(FILTROS)

        bgr_frame = render_portal(bgr_frame, p1, p2, p3, p4, FILTROS[filtro_index])

    # Convert back to RGB for Gradio output
    return cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB), filtro_index, closing_detector

def get_initial_state():
    return 0, ClosingGestureDetector()

with gr.Blocks() as interface:
    gr.Markdown("# AR Portal Filters")
    gr.Markdown("Make a pinch gesture with both hands to create a portal. Close the portal to change the filter.")

    filtro_state = gr.State(0)
    closing_state = gr.State(ClosingGestureDetector)

    with gr.Row():
        input_image = gr.Image(sources=["webcam"], streaming=True)
        output_image = gr.Image()

    interface.load(get_initial_state, inputs=None, outputs=[filtro_state, closing_state])

    input_image.stream(
        fn=process_frame,
        inputs=[input_image, filtro_state, closing_state],
        outputs=[output_image, filtro_state, closing_state]
    )

if __name__ == "__main__":
    interface.launch(server_name="0.0.0.0")
