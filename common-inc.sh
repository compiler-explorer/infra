
get_conf() {
  if [[ "$FAKEAWS" == "1" ]]; then
    if [[ "$1" == "/compiler-explorer/logDestHost" ]]; then echo "127.0.0.1"; fi
    if [[ "$1" == "/compiler-explorer/logDestPort" ]]; then echo "80"; fi
    if [[ "$1" == "/compiler-explorer/cefsroot" ]]; then echo "fakecefsroot123"; fi
    if [[ "$1" == "/compiler-explorer/promPassword" ]]; then echo "prompwd123"; fi
    if [[ "$1" == "/compiler-explorer/lokiPassword" ]]; then echo "lokipwd123"; fi
  else
    aws ssm get-parameter --name "$1" | jq -r .Parameter.Value
  fi
}
