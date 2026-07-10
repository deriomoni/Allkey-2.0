import { useRef, useState, DragEvent } from 'react'

interface FileUploadProps {
  label: string
  accept?: string
  onFileSelect: (file: File) => void
  selectedFile: File | null
}

export default function FileUpload({ label, accept = '.xlsx,.xls', onFileSelect, selectedFile }: FileUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)

  const handleClick = () => {
    inputRef.current?.click()
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      onFileSelect(file)
    }
  }

  const handleDragOver = (e: DragEvent) => {
    e.preventDefault()
    setDragOver(true)
  }

  const handleDragLeave = (e: DragEvent) => {
    e.preventDefault()
    setDragOver(false)
  }

  const handleDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files?.[0]
    if (file) {
      onFileSelect(file)
    }
  }

  return (
    <div
      className={`file-upload ${dragOver ? 'dragover' : ''}`}
      onClick={handleClick}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        onChange={handleChange}
      />
      {selectedFile ? (
        <div>
          <strong>{selectedFile.name}</strong>
          <p style={{ color: '#6b7280', marginTop: 4 }}>
            {(selectedFile.size / 1024).toFixed(1)} KB
          </p>
        </div>
      ) : (
        <div>
          <p style={{ marginBottom: 8 }}><strong>{label}</strong></p>
          <p style={{ color: '#6b7280' }}>Перетащите файл сюда или нажмите для выбора</p>
        </div>
      )}
    </div>
  )
}
