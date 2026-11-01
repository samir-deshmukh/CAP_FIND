# CAPFind server-side PDF extraction

## No-card workflow

1. Open the CAPFind admin Import Center.
2. Select PDF files (up to 50 MiB each) and click **Upload and Queue**.
3. The server queues extraction jobs and processes them sequentially in bounded page chunks.
4. Inspect validation results in the Review Center and explicitly approve data before publishing.

## Storage warning

The no-card configuration uses the host filesystem. On Render's free tier this storage is ephemeral and may be cleared on restart or deployment. Keep the original PDFs on your PC or in Drive until processing and review are complete. CAPFind does not delete originals from Drive.

For persistent server-side source retention, configure private durable object storage separately; do not enable a paid service or add a payment method unless you have intentionally decided to do so.
