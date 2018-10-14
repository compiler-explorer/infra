set fish_greeting

if not echo $fish_user_paths | grep /home/ubuntu/compiler-explorer-image/bin
    set -U fish_user_paths $fish_user_paths /home/ubuntu/compiler-explorer-image/bin
end

set -Ux EDITOR /usr/bin/vim

mkdir -p ~/.config/fish/
echo begin >> ~/.config/fish/config.fish
echo   set --local AUTOJUMP_PATH /usr/share/autojump/autojump.fish >> ~/.config/fish/config.fish
echo   if test -e \$AUTOJUMP_PATH >> ~/.config/fish/config.fish
echo     source \$AUTOJUMP_PATH >> ~/.config/fish/config.fish
echo   end >> ~/.config/fish/config.fish
echo end >> ~/.config/fish/config.fish
