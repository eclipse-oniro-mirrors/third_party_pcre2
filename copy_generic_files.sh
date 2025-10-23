#! /bin/bash

pcre2_lib_dir=$1
pcre2_gen_dir=$2

function check_md5_and_copy() {
    echo "check_md5_and_copy $1 $2"
    check_config_result=$(bash $pcre2_lib_dir/check_md5.sh $1 $2)
    echo "${check_config_result}x"
    if [[ "${check_config_result}x" == "x" ]];then
        cp -f $1 $2
    fi
}

mkdir -P $pcre2_lib_dir/src
check_md5_and_copy $pcre2_lib_dir/src/config.h.generic $pcre2_gen_dir/src/config.h
check_md5_and_copy $pcre2_lib_dir/src/pcre2.h.generic $pcre2_gen_dir/src/pcre2.h
check_md5_and_copy $pcre2_lib_dir/src/pcre2_chartables.c.dist $pcre2_gen_dir/src/pcre2_chartables.c
