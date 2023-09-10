from lib.amazon import dynamodb_client

class NightlyVersions:
    table_name: str = "nightly-version"

    def update_version(self, exe: str, modified: str, version: str, full_version: str):
        dynamodb_client.put_item(
            TableName=self.table_name,
            Item={
                "exe": {"S": exe},
                "modified": {"N": modified},
                "version": {"S": version},
                "full_version": {"S": full_version}
            }
        )
        return

    def get_version(self, exe: str):
        result = dynamodb_client.get_item(
            TableName=self.table_name,
            Key={"exe": {"S": exe}},
            ConsistentRead=True,
        )
        item = result.get("Item")
        if item:
            return {
                "exe": item["exe"]["S"],
                "version": item["version"]["S"],
                "full_version": item["full_version"]["S"],
                "modified": item["modified"]["N"]}
        else:
            None
