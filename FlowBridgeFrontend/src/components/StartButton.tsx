import "../App.css";

interface StartButtonProps {
  onClick?: () => void;
  disabled?: boolean;
  isLoading?: boolean;
}

export default function StartButton({ onClick, disabled = false, isLoading = false }: StartButtonProps) {
  return (
    <div className="headingCenter">
      <button
        className="startButton"
        onClick={onClick}
        disabled={disabled || isLoading}
        title={isLoading ? "Generating Flowchart..." : disabled ? "Upload a file or zip first" : "Generate Flowchart"}
        style={{
          cursor: disabled || isLoading ? "not-allowed" : "pointer",
          opacity: disabled ? 0.45 : isLoading ? 0.75 : 1,
          transition: "transform 0.15s, opacity 0.2s",
          animation: isLoading ? "pulse 1.2s infinite ease-in-out" : "none",
        }}
      >
        <img src="./StartButton.png" alt="Start Button" />
      </button>
    </div>
  );
}
