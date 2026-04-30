import React, { useEffect } from "react"
import { Input } from "antd"
import { useContext } from "react"
import { SearchContext } from '../context/SearchContext';

interface SearchProps {
    onSubmit: (search: string) => void;
}

const Search: React.FC<SearchProps> = ({ onSubmit }) => {

    const searchContext = useContext(SearchContext);

    if (!searchContext) {
        throw new Error("Search component must be used within a SearchProvider");
    }

    const { searchTerm, setSearchTerm } = searchContext;

    useEffect(() => {
        // Set up a timer to call the onSubmit function
        const timerId = setTimeout(() => {
            onSubmit(searchTerm);
        }, 1500); // 1.5-second debounce delay

        // This is the cleanup function.
        // It runs when the component unmounts or before the effect runs again.
        // This clears the previous timer, so the search only happens
        // after the user has stopped typing.
        return () => {
            clearTimeout(timerId);
        };
    }, [searchTerm, onSubmit]); // Re-run the effect when searchTerm or onSubmit changes

    return (
        <>
            <Input
                value={searchTerm}
                allowClear
                className='w-full min-w-0 md:min-w-[300px] md:w-[50%]'
                placeholder='Search by name or username'
                onChange={e => setSearchTerm(e.target.value)}
            // The onKeyDown for Enter is no longer needed for search,
            // as the search will trigger automatically after the user stops typing.
            />
        </>
    )
}

export default Search