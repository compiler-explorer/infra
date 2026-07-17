# Runner Debugging

Execute arbitrary commands and debug issues on our self-hosted GitHub runners. Remember it takes a while for the workflow to be picked up by a runner, so be patient. The keys you use for committing to github are used to authenticate to the SSH server.

## Commands

### Quick Commands

Run single commands on linux-x64 runners:

```bash
ce workflows run-adhoc --command "ls -la /opt"
ce workflows run-adhoc --command "uname -a && free -h"
ce workflows run-adhoc --dry-run --command "your-command"  # preview only
```

Interactive is probably more useful:

### Interactive Debugging

Start SSH debugging session:

```bash
ce workflows run-adhoc --interactive                       # 30 min timeout
ce workflows run-adhoc --interactive --timeout-minutes 60  # custom timeout
```

**Warning**: Interactive sessions consume runner resources until manually cancelled.

## Connecting to Interactive Sessions

1. Trigger workflow:
   ```bash
   ce workflows run-adhoc --interactive
   ```

2. Get SSH connection from GitHub Actions logs:
   - Navigate to running workflow in GitHub Actions
   - Open "Setup interactive session" step
   - Copy SSH command from the "connection" box in the output

3. Connect:
   ```bash
   ssh <MAGICVALUEPASTEDFROMLOG>@uptermd.upterm.dev
   ```

The session runs in tmux with full runner access.

## Stopping Interactive Sessions

Interactive sessions continue consuming resources after SSH disconnection. Always cancel manually.

### Cancel Workflow (Recommended)

```bash
ce workflows status --workflow adhoc-command.yml --status in_progress
gh run cancel <RUN_ID> -R github.com/compiler-explorer/infra
```

### Via GitHub UI

1. Navigate to Actions tab
2. Find running "Run Ad-hoc Command" workflow
3. Click "Cancel workflow"

### SSH Exit

Typing `exit` closes SSH connection but leaves workflow running. Only use if reconnecting.

## Security

- Access restricted to authorized users (defined in workflow file)
- SSH access limited to workflow trigger user
- All activity logged in GitHub Actions

## Troubleshooting

- **Runner unavailable**: Self-hosted runners start on demand. Retry after a few minutes.
- **Permission denied**: Verify your GitHub user is in the workflow's allowed users list.
- **SSH connection fails**: Use exact SSH command from workflow logs. Ensure your local SSH keys are added to GitHub.
