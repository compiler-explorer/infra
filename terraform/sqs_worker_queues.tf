
resource "aws_sqs_queue" "staging-execqueue-aarch64-linux-cpu" {
  name                        = "staging-execqueue-aarch64-linux-cpu.fifo"
  fifo_queue                  = true
  content_based_deduplication = false
}

resource "aws_sqs_queue" "prod-execqueue-aarch64-linux-cpu" {
  name                        = "prod-execqueue-aarch64-linux-cpu.fifo"
  fifo_queue                  = true
  content_based_deduplication = false
}
