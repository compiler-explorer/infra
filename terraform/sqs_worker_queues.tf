
resource "aws_sqs_queue" "execqueue-aarch64-linux-cpu" {
  name                        = "execqueue-aarch64-linux-cpu.fifo"
  fifo_queue                  = true
  content_based_deduplication = false
}
