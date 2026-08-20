add_library(TypeTrixTsf SHARED
    TypeTrixTsf.cpp
    TypeTrixTsf.def
)

target_link_libraries(TypeTrixTsf PRIVATE
    typetrix_core
    msctf
    ole32
    advapi32
    uuid
)

target_compile_definitions(TypeTrixTsf PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX)

set_target_properties(TypeTrixTsf PROPERTIES
    OUTPUT_NAME "TypeTrixTsf"
)
