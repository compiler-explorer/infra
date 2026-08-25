# Athena / Glue: the catalog tables that describe our log data, and the
# workgroup the stats CLIs (bin/lib/cli/compiler_stats.py, library_stats.py)
# query through. Adopted from the console, see infra#2330.

resource "aws_glue_catalog_database" "default" {
  name = "default"

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_athena_workgroup" "primary" {
  name  = "primary"
  state = "ENABLED"

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = false
    requester_pays_enabled             = false

    result_configuration {
      output_location = "s3://${aws_s3_bucket.compiler-explorer-logs.bucket}/athena-results/"
    }

    engine_version {
      selected_engine_version = "AUTO"
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}

# ALB access logs, as shipped by the load balancer. Queried by `ce compiler_stats`.
resource "aws_glue_catalog_table" "alb_logs" {
  name          = "alb_logs"
  database_name = aws_glue_catalog_database.default.name

  table_type = "EXTERNAL_TABLE"

  parameters = {
    "EXTERNAL" = "TRUE"
  }

  storage_descriptor {
    location      = "s3://compiler-explorer-logs/elb/AWSLogs/052730242331/elasticloadbalancing/us-east-1"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.serde2.RegexSerDe"

      parameters = {
        "serialization.format" = "1"
        "input.regex"          = "([^ ]*) ([^ ]*) ([^ ]*) ([^ ]*):([0-9]*) ([^ ]*)[:-]([0-9]*) ([-.0-9]*) ([-.0-9]*) ([-.0-9]*) (|[-0-9]*) (-|[-0-9]*) ([-0-9]*) ([-0-9]*) \"([^ ]*) ([^ ]*) (- |[^ ]*)\" \"([^\"]*)\" ([A-Z0-9-]+) ([A-Za-z0-9.-]*) ([^ ]*) \"([^\"]*)\" \"([^\"]*)\" \"([^\"]*)\" ([-.0-9]*) ([^ ]*) \"([^\"]*)\" \"([^\"]*)\"($| \"[^ ]*\")(.*)"
      }
    }

    columns {
      name = "type"
      type = "string"
    }

    columns {
      name = "time"
      type = "string"
    }

    columns {
      name = "elb"
      type = "string"
    }

    columns {
      name = "client_ip"
      type = "string"
    }

    columns {
      name = "client_port"
      type = "int"
    }

    columns {
      name = "target_ip"
      type = "string"
    }

    columns {
      name = "target_port"
      type = "int"
    }

    columns {
      name = "request_processing_time"
      type = "double"
    }

    columns {
      name = "target_processing_time"
      type = "double"
    }

    columns {
      name = "response_processing_time"
      type = "double"
    }

    columns {
      name = "elb_status_code"
      type = "string"
    }

    columns {
      name = "target_status_code"
      type = "string"
    }

    columns {
      name = "received_bytes"
      type = "bigint"
    }

    columns {
      name = "sent_bytes"
      type = "bigint"
    }

    columns {
      name = "request_verb"
      type = "string"
    }

    columns {
      name = "request_url"
      type = "string"
    }

    columns {
      name = "request_proto"
      type = "string"
    }

    columns {
      name = "user_agent"
      type = "string"
    }

    columns {
      name = "ssl_cipher"
      type = "string"
    }

    columns {
      name = "ssl_protocol"
      type = "string"
    }

    columns {
      name = "target_group_arn"
      type = "string"
    }

    columns {
      name = "trace_id"
      type = "string"
    }

    columns {
      name = "domain_name"
      type = "string"
    }

    columns {
      name = "chosen_cert_arn"
      type = "string"
    }

    columns {
      name = "matched_rule_priority"
      type = "string"
    }

    columns {
      name = "request_creation_time"
      type = "string"
    }

    columns {
      name = "actions_executed"
      type = "string"
    }

    columns {
      name = "redirect_url"
      type = "string"
    }

    columns {
      name = "lambda_error_reason"
      type = "string"
    }

    columns {
      name = "new_field"
      type = "string"
    }
  }
}

# CloudFront standard logs. Queried by `ce library_stats` and most of the saved queries.
resource "aws_glue_catalog_table" "cloudfront_logs" {
  name          = "cloudfront_logs"
  database_name = aws_glue_catalog_database.default.name

  table_type = "EXTERNAL_TABLE"

  parameters = {
    "skip.header.line.count" = "2"
    "EXTERNAL"               = "TRUE"
  }

  storage_descriptor {
    location      = "s3://compiler-explorer-logs/cloudfront"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.serde2.lazy.LazySimpleSerDe"

      parameters = {
        "serialization.format" = "\t"
        "field.delim"          = "\t"
      }
    }

    columns {
      name = "date"
      type = "date"
    }

    columns {
      name = "time"
      type = "string"
    }

    columns {
      name = "location"
      type = "string"
    }

    columns {
      name = "bytes"
      type = "bigint"
    }

    columns {
      name = "request_ip"
      type = "string"
    }

    columns {
      name = "method"
      type = "string"
    }

    columns {
      name = "host"
      type = "string"
    }

    columns {
      name = "uri"
      type = "string"
    }

    columns {
      name = "status"
      type = "int"
    }

    columns {
      name = "referrer"
      type = "string"
    }

    columns {
      name = "user_agent"
      type = "string"
    }

    columns {
      name = "query_string"
      type = "string"
    }

    columns {
      name = "cookie"
      type = "string"
    }

    columns {
      name = "result_type"
      type = "string"
    }

    columns {
      name = "request_id"
      type = "string"
    }

    columns {
      name = "host_header"
      type = "string"
    }

    columns {
      name = "request_protocol"
      type = "string"
    }

    columns {
      name = "request_bytes"
      type = "bigint"
    }

    columns {
      name = "time_taken"
      type = "float"
    }

    columns {
      name = "xforwarded_for"
      type = "string"
    }

    columns {
      name = "ssl_protocol"
      type = "string"
    }

    columns {
      name = "ssl_cipher"
      type = "string"
    }

    columns {
      name = "response_result_type"
      type = "string"
    }

    columns {
      name = "http_version"
      type = "string"
    }

    columns {
      name = "fle_status"
      type = "string"
    }

    columns {
      name = "fle_encrypted_fields"
      type = "int"
    }
  }
}

# Page-load / sponsor-view events written by the stats lambda (lambda/stats.py).
resource "aws_glue_catalog_table" "stats" {
  name          = "stats"
  database_name = aws_glue_catalog_database.default.name

  table_type = "EXTERNAL_TABLE"

  parameters = {
    "EXTERNAL" = "TRUE"
  }

  storage_descriptor {
    location      = "s3://compiler-explorer-logs/stats"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.IgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"

      parameters = {
        "serialization.format" = "1"
      }
    }

    columns {
      name = "date"
      type = "date"
    }

    columns {
      name = "time"
      type = "string"
    }

    columns {
      name = "type"
      type = "string"
    }

    columns {
      name = "value"
      type = "string"
    }
  }
}

# CloudTrail events for the account (see audit.tf for the trail itself).
resource "aws_glue_catalog_table" "cloudtrail_logs" {
  name          = "cloudtrail_logs_cloudtrailgodboltorg"
  database_name = aws_glue_catalog_database.default.name

  table_type = "EXTERNAL_TABLE"

  parameters = {
    "comment"        = "CloudTrail table for cloudtrail.godbolt.org bucket"
    "EXTERNAL"       = "TRUE"
    "classification" = "cloudtrail"
  }

  storage_descriptor {
    location      = "s3://cloudtrail.godbolt.org/AWSLogs/052730242331/CloudTrail"
    input_format  = "com.amazon.emr.cloudtrail.CloudTrailInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hive.hcatalog.data.JsonSerDe"

      parameters = {
        "serialization.format" = "1"
      }
    }

    columns {
      name = "eventversion"
      type = "string"
    }

    columns {
      name = "useridentity"
      type = "struct<type:string,principalId:string,arn:string,accountId:string,invokedBy:string,accessKeyId:string,userName:string,sessionContext:struct<attributes:struct<mfaAuthenticated:string,creationDate:string>,sessionIssuer:struct<type:string,principalId:string,arn:string,accountId:string,username:string>,ec2RoleDelivery:string,webIdFederationData:map<string,string>>>"
    }

    columns {
      name = "eventtime"
      type = "string"
    }

    columns {
      name = "eventsource"
      type = "string"
    }

    columns {
      name = "eventname"
      type = "string"
    }

    columns {
      name = "awsregion"
      type = "string"
    }

    columns {
      name = "sourceipaddress"
      type = "string"
    }

    columns {
      name = "useragent"
      type = "string"
    }

    columns {
      name = "errorcode"
      type = "string"
    }

    columns {
      name = "errormessage"
      type = "string"
    }

    columns {
      name = "requestparameters"
      type = "string"
    }

    columns {
      name = "responseelements"
      type = "string"
    }

    columns {
      name = "additionaleventdata"
      type = "string"
    }

    columns {
      name = "requestid"
      type = "string"
    }

    columns {
      name = "eventid"
      type = "string"
    }

    columns {
      name = "resources"
      type = "array<struct<arn:string,accountId:string,type:string>>"
    }

    columns {
      name = "eventtype"
      type = "string"
    }

    columns {
      name = "apiversion"
      type = "string"
    }

    columns {
      name = "readonly"
      type = "string"
    }

    columns {
      name = "recipientaccountid"
      type = "string"
    }

    columns {
      name = "serviceeventdetails"
      type = "string"
    }

    columns {
      name = "sharedeventid"
      type = "string"
    }

    columns {
      name = "vpcendpointid"
      type = "string"
    }

    columns {
      name = "tlsdetails"
      type = "struct<tlsVersion:string,cipherSuite:string,clientProvidedHostHeader:string>"
    }
  }
}

# Per-compilation stats written by the CE app itself (lib/stats.ts): hive-style
# year=/month=/date= paths, month being 0-based because it comes from getUTCMonth().
resource "aws_glue_catalog_table" "compile_stats" {
  name          = "compile_stats"
  database_name = aws_glue_catalog_database.default.name

  table_type = "EXTERNAL_TABLE"

  parameters = {
    "EXTERNAL" = "TRUE"
    # month is 0-based (getUTCMonth)
    "projection.enabled"        = "true"
    "projection.year.type"      = "integer"
    "projection.year.range"     = "2024,2040"
    "projection.month.type"     = "integer"
    "projection.month.range"    = "0,11"
    "projection.date.type"      = "integer"
    "projection.date.range"     = "1,31"
    "storage.location.template" = "s3://compiler-explorer-logs/compile-stats/year=$${year}/month=$${month}/date=$${date}/"
  }

  partition_keys {
    name = "year"
    type = "int"
  }

  partition_keys {
    name = "month"
    type = "int"
  }

  partition_keys {
    name = "date"
    type = "int"
  }

  storage_descriptor {
    location      = "s3://compiler-explorer-logs/compile-stats"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"

      parameters = {
        "serialization.format"  = "1"
        "case.insensitive"      = "TRUE"
        "dots.in.keys"          = "FALSE"
        "ignore.malformed.json" = "FALSE"
        "mapping"               = "TRUE"
      }
    }

    columns {
      name = "time"
      type = "string"
    }

    columns {
      name = "compilerid"
      type = "string"
    }

    columns {
      name = "sourcehash"
      type = "string"
    }

    columns {
      name = "executionparamshash"
      type = "string"
    }

    columns {
      name = "bypasscache"
      type = "boolean"
    }

    columns {
      name = "options"
      type = "array<string>"
    }

    columns {
      name = "filters"
      type = "struct<binary:boolean,binaryobject:boolean,execute:boolean,demangle:boolean,intel:boolean,labels:boolean>"
    }

    columns {
      name = "backendoptions"
      type = "array<string>"
    }

    columns {
      name = "libraries"
      type = "array<string>"
    }

    columns {
      name = "tools"
      type = "array<string>"
    }

    columns {
      name = "overrides"
      type = "array<string>"
    }

    columns {
      name = "runtimetools"
      type = "array<string>"
    }

    columns {
      name = "buildmethod"
      type = "string"
    }
  }
}

moved {
  from = aws_glue_catalog_table.compile_stats_table
  to   = aws_glue_catalog_table.compile_stats
}
