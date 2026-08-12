interface ConversionResultProps {
  downloadUrl: string;
  filename: string;
  onReset: () => void;
}

export default function ConversionResult({ downloadUrl, filename, onReset }: ConversionResultProps) {
  return (
    <div className="flex flex-col items-center gap-3 text-center">
      <p className="text-sm font-medium text-green-600 dark:text-green-400">
        Conversion complete
      </p>
      <a
        href={downloadUrl}
        download={filename}
        className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
      >
        Download {filename}
      </a>
      <button
        onClick={onReset}
        className="text-xs text-neutral-500 underline hover:text-neutral-700 dark:hover:text-neutral-300"
      >
        Convert another file
      </button>
    </div>
  );
}
