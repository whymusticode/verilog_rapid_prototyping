# Source this file to complete convert.py's -m/--model argument in Bash.
_vrp_convert_model_completion() {
    local current="${COMP_WORDS[COMP_CWORD]}"
    local previous="${COMP_WORDS[COMP_CWORD-1]}"
    local script="${COMP_WORDS[0]}"
    local -a command=("$script")

    if [[ "${script##*/}" == python || "${script##*/}" == python3 ]]; then
        script="${COMP_WORDS[1]}"
        if [[ "${script##*/}" != convert.py ]]; then
            mapfile -t COMPREPLY < <(compgen -f -- "$current")
            return
        fi
        command+=("$script")
    fi

    if [[ "$previous" == -m || "$previous" == --model ]]; then
        mapfile -t COMPREPLY < <("${command[@]}" --complete-models "$current")
        if [[ "${COMPREPLY[*]}" == "codex:" ]]; then
            compopt -o nospace
        fi
    else
        mapfile -t COMPREPLY < <(compgen -f -- "$current")
    fi
}

complete -F _vrp_convert_model_completion python python3 convert.py ./convert.py
