set fish_greeting

if not echo $fish_user_path | grep /home/ubuntu/compiler-explorer-image/bin
    set -U fish_user_path $fish_user_path /home/ubuntu/compiler-explorer-image/bin
end
