import cv2

# Initialize camera
cap = cv2.VideoCapture(0)

# MOG2 BackSub
# history: 500 = keeps 500 frames of background history
# varThreshold: 50 = Sensitivity. LOWER is more sensitive, HIGHER is less.
# Try setting this to 20 if 50 isn't working for you.
backSub = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=50, detectShadows=True)

while True:
    ret, frame = cap.read()
    if not ret: break

    # Update background model
    fgMask = backSub.apply(frame)
    
    # Optional: Remove small noise
    _, fgMask = cv2.threshold(fgMask, 200, 255, cv2.THRESH_BINARY)

    # Show the windows
    cv2.imshow("Original Feed", frame)
    cv2.imshow("Motion Mask (What the computer sees)", fgMask)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()