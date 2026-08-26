interface ProgressBarProps {
  percent: number;
}

export default function ProgressBar({ percent }: ProgressBarProps) {
  return (
    <div className="w-full">
      <div className="h-2 w-full overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-800">
        <div
          className="h-full rounded-full bg-blue-600 transition-all duration-150"
          style={{ width: `${percent}%` }}
        />
      </div>
      <p className="mt-1 text-xs text-neutral-500">{percent}%</p>
    </div>
  );
}
